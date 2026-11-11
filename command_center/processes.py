"""Launch saved scripts in their native Windows consoles."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


class ProcessLaunchError(RuntimeError):
    pass


def enumerate_visible_windows() -> list[dict[str, object]]:
    """Return titled top-level windows that can be selected as paste targets."""
    if os.name != "nt":
        raise ProcessLaunchError("La selección de ventanas está disponible en Windows.")

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [enum_proc, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.GetCurrentProcessId.restype = wintypes.DWORD
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    own_pid = kernel32.GetCurrentProcessId()
    windows: list[dict[str, object]] = []

    def process_name(pid: int) -> str:
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return f"PID {pid}"
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return os.path.basename(buffer.value)
            return f"PID {pid}"
        finally:
            kernel32.CloseHandle(handle)

    @enum_proc
    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
        title = title_buffer.value.strip()
        if not title:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != own_pid:
            windows.append({"handle": int(hwnd), "title": title,
                            "process": process_name(pid.value), "pid": int(pid.value)})
        return True

    user32.EnumWindows(visit, 0)
    windows.sort(key=lambda item: (str(item["title"]).casefold(), str(item["process"]).casefold()))
    return windows


def paste_text_into_window(window_handle: int, text: str) -> str:
    """Paste into the selected foreground window without sending Enter."""
    if os.name != "nt":
        raise ProcessLaunchError("Pegar en una ventana está disponible en Windows.")
    if not text:
        raise ProcessLaunchError("No hay texto para pegar.")

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.restype = wintypes.HWND
    hwnd = wintypes.HWND(window_handle)
    if not user32.IsWindow(hwnd):
        raise ProcessLaunchError("La ventana seleccionada ya no está disponible.")
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    title_buffer = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
    user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))

    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    if not user32.SetForegroundWindow(hwnd):
        raise ProcessLaunchError("Windows no permitió activar la ventana seleccionada.")
    time.sleep(0.18)
    foreground = user32.GetForegroundWindow()
    if int(foreground or 0) != window_handle:
        raise ProcessLaunchError("La ventana elegida no quedó activa; no se pegó el texto.")

    class KeyboardInput(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    class MouseInput(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class HardwareInput(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD)]

    class InputUnion(ctypes.Union):
        _fields_ = [("mi", MouseInput), ("ki", KeyboardInput), ("hi", HardwareInput)]

    class Input(ctypes.Structure):
        _anonymous_ = ("union",)
        _fields_ = [("type", wintypes.DWORD), ("union", InputUnion)]

    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    events = (Input * 4)()
    for index, (virtual_key, flags) in enumerate(((0x11, 0), (0x56, 0),
                                                  (0x56, 0x0002), (0x11, 0x0002))):
        events[index].type = 1  # INPUT_KEYBOARD
        events[index].ki.wVk = virtual_key
        events[index].ki.dwFlags = flags
    inserted = user32.SendInput(len(events), events, ctypes.sizeof(Input))
    if inserted != len(events):
        # Best effort to avoid leaving a modifier pressed if input was partially inserted.
        release = (Input * 2)()
        for index, virtual_key in enumerate((0x56, 0x11)):
            release[index].type = 1
            release[index].ki.wVk = virtual_key
            release[index].ki.dwFlags = 0x0002
        user32.SendInput(len(release), release, ctypes.sizeof(Input))
        raise ProcessLaunchError(
            "Windows bloqueó el pegado. Comprueba que la aplicación de destino no esté "
            "ejecutándose con permisos más altos que Command Center."
        )
    return title_buffer.value or "ventana seleccionada"


def _python_interpreter() -> str:
    candidate = shutil.which("python") or shutil.which("py")
    if not candidate:
        raise ProcessLaunchError("No se encontró Python en PATH. Instala Python o configura su acceso.")
    return candidate


def launch_script(runner: str, script: str) -> None:
    """Launch script without routing its text through an extra shell parser."""
    if not script.strip():
        raise ProcessLaunchError("El comando está vacío.")
    if os.name != "nt":
        raise ProcessLaunchError("La ejecución de consolas está disponible en Windows.")

    suffix = {"PowerShell": ".ps1", "CMD": ".cmd", "Python": ".py"}.get(runner)
    if not suffix:
        raise ProcessLaunchError(f"Motor no reconocido: {runner}")

    encoding = "utf-8-sig" if runner == "PowerShell" else "utf-8"
    handle = tempfile.NamedTemporaryFile(mode="w", encoding=encoding, suffix=suffix, delete=False)
    script_path = Path(handle.name)
    launcher_path: Path | None = None
    paths_to_clean = [script_path]
    try:
        handle.write(script)
        if runner == "CMD":
            handle.write("\n")
            handle.write("echo.\npause\n")
        handle.close()

        if runner == "PowerShell":
            program = shutil.which("powershell.exe") or "powershell.exe"
            arguments = [program, "-NoLogo", "-NoExit", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
        elif runner == "CMD":
            program = os.environ.get("COMSPEC", "cmd.exe")
            arguments = [program, "/K", str(script_path)]
        else:
            program = _python_interpreter()
            launcher = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".cmd", delete=False)
            launcher_path = Path(launcher.name)
            launcher.write(f'"{program}" "{script_path}"\necho.\npause\n')
            launcher.close()
            paths_to_clean.append(launcher_path)
            program = os.environ.get("COMSPEC", "cmd.exe")
            arguments = [program, "/K", str(launcher_path)]

        creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        process = subprocess.Popen(arguments, shell=False, creationflags=creation_flags)
    except Exception as exc:
        try:
            handle.close()
        except Exception:
            pass
        for temporary_path in paths_to_clean:
            temporary_path.unlink(missing_ok=True)
        if isinstance(exc, ProcessLaunchError):
            raise
        raise ProcessLaunchError(str(exc)) from exc

    def cleanup_after_exit() -> None:
        try:
            process.wait()
        finally:
            for temporary_path in paths_to_clean:
                temporary_path.unlink(missing_ok=True)

    threading.Thread(target=cleanup_after_exit, name="command-center-script-cleanup", daemon=True).start()
