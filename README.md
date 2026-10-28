<div align="center">

  <img src="app_icon.ico" alt="CommandCenter" width="100" height="100" />

  # CommandCenter

  **Guarda, organiza y ejecuta tus comandos, notas y enlaces desde una sola ventana.**

  [![Python](https://img.shields.io/badge/python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](#-requisitos)
  [![License](https://img.shields.io/badge/license-MIT-2EA44F.svg)](LICENSE)
  [![Version](https://img.shields.io/badge/version-2.0.15-F59E0B.svg)](command_center/__init__.py)
  [![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D4.svg?logo=windows&logoColor=white)](#-requisitos)
  [![Qt](https://img.shields.io/badge/Qt-PySide6%206.12-41CD52.svg?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)

  <p>
    <a href="#-características">Características</a> ·
    <a href="#-instalación">Instalación</a> ·
    <a href="#-uso">Uso</a> ·
    <a href="#-compilar-el-exe">Compilar</a> ·
    <a href="#-licencia">Licencia</a>
  </p>

</div>

---

## ✨ Descripción

**CommandCenter** es una aplicación de escritorio para Windows que reúne en un único lugar tus comandos de PowerShell, CMD y Python, junto con notas, enlaces y colecciones personalizadas.

Todo se guarda en una base de datos **SQLite local**. No requiere cuenta, no usa servicios externos y funciona sin conexión.

---

## 🚀 Características

| | Función | Descripción |
|:-:|---|---|
| 📚 | **Colecciones** | Comandos, juegos, notas y hardware, enlaces y pestañas propias. Búsqueda, filtros por categoría y orden manual o automático. |
| 🧩 | **Parámetros** | Los marcadores `{{nombre}}` piden su valor antes de ejecutar y muestran la vista previa del comando final. |
| ▶️ | **Ejecución** | Cada comando se abre en su propia consola (PowerShell, CMD o Python) o se pega en la ventana que elijas. |
| 🧠 | **Organización** | Sugerencias locales de títulos, categorías y pestañas, detección de duplicados, edición por lote y archivado. |
| 📥 | **Importación y exportación** | Importa texto plano o JSON de forma aditiva, sin sustituir datos existentes, y exporta a JSON. |
| 💾 | **Copias de seguridad** | Copias manuales y automáticas de la base. Se conservan las 10 más recientes. |
| 🎨 | **Cuatro interfaces** | Clásica, Compacta, Tabla y Consola, con tema claro y oscuro. |

---

## 📁 Estructura del proyecto

```plaintext
CommandCenter/
├── command_center/              # Paquete de la aplicación
│   ├── __init__.py              # Versión
│   ├── app.py                   # Ventana principal, colecciones y tarjetas
│   ├── dialogs.py               # Diálogos y pantallas de opciones
│   ├── suggestions.py           # Sugerencias e importación de texto (sin Qt)
│   ├── constants.py             # Constantes compartidas
│   ├── processes.py             # Ejecución de scripts y pegado en ventanas (Win32)
│   ├── storage.py               # Base SQLite, importación, exportación y copias
│   └── ui/                      # Estilos, widgets y resaltado de sintaxis
├── licenses/                    # Textos de licencia y avisos de terceros
├── app_icon.ico                 # Icono de la aplicación
├── build_exe.bat                # Compilación en Windows
├── build_exe.py                 # Script de PyInstaller
├── main.py                      # Punto de entrada
├── requirements.lock            # Versiones exactas de las dependencias
├── LICENSE                      # Licencia MIT
└── README.md
```

---

## 🧭 Requisitos

- 🐍 **Python** 3.10 o superior.
- 🪟 **Windows** 10 u 11. Ejecutar comandos, pegar en ventanas y compilar el EXE solo funcionan en Windows.

---

## 📦 Instalación

**1. Clona el repositorio**

```powershell
git clone https://github.com/elkekito/CommandCenter.git
cd CommandCenter
```

**2. Crea y activa un entorno virtual**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**3. Instala las versiones exactas de las dependencias**

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
```

> ¿Solo quieres usar la aplicación? Descarga `CommandCenter.exe` desde la sección **Releases** del repositorio. No necesitas Python.

---

## ▶️ Uso

Para ejecutar la aplicación desde el código fuente:

```powershell
python main.py
```

En el primer inicio, la aplicación pregunta dónde guardar la base de datos y qué interfaz usar. Ambas opciones se pueden cambiar después desde **Opciones**.

---

## 🛠️ Compilar el EXE

Con el entorno virtual activo, desde la raíz del proyecto:

```powershell
.\build_exe.bat
```

El resultado es `dist\CommandCenter.exe`, un ejecutable de un solo archivo.

Antes de generar el ejecutable, la compilación comprueba que las versiones instaladas coinciden con `requirements.lock` y que el paquete no incluye Qt Virtual Keyboard ni Qt PDF. Si alguna comprobación falla, no se genera el ejecutable.

---

## ⚖️ Licencia

El código de CommandCenter se distribuye bajo la **licencia MIT**. Consulta [LICENSE](LICENSE).

Las dependencias de terceros, en particular Qt y PySide6 bajo **LGPLv3**, tienen sus propias licencias. Sus textos y los avisos correspondientes están en [`licenses/`](licenses/), con el detalle en [`THIRD-PARTY-NOTICES.md`](licenses/THIRD-PARTY-NOTICES.md).

---

<div align="center">

  Hecho con PySide6 y SQLite · MIT

</div>
