# Avisos de software de terceros

CommandCenter se distribuye como un único ejecutable Windows. El código propio se publica bajo la licencia MIT (`LICENSE`). El ejecutable incluye los componentes de terceros que se indican aquí.

Este documento describe la versión 2.0.13 y las posteriores, compiladas con `build_exe.py`. El análisis de versiones anteriores está en el historial de Git.

## Componentes principales

| Componente | Versión | Licencia declarada | Textos incluidos |
|---|---|---|---|
| Qt for Python (PySide6_Essentials, incluye Qt 6.12.0) | 6.12.0 | `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` | `licenses/LGPL-3.0-only.txt`, `licenses/GPL-3.0-only.txt` |
| Shiboken6 | 6.12.0 | Igual que PySide6 | Igual que PySide6 |
| Python (runtime y biblioteca estándar) | 3.13.15 | PSF-2.0 | `licenses/PSF-2.0.txt` |
| Bootloader de PyInstaller | 6.22.3 | GPLv2 o posterior, con la excepción de PyInstaller para aplicaciones empaquetadas | [Licencia de PyInstaller](https://pyinstaller.org/en/stable/license.html) |
| Runtime de Microsoft Visual C++ (`MSVCP140*`, `VCRUNTIME140*`) | Según Visual Studio | Términos de Microsoft | No es una licencia de código abierto |

Cada fichero del ejecutable tiene un paquete de origen, una licencia declarada en sus metadatos y un SHA-256. Ese inventario se genera al compilar y no se publica en el repositorio.

## Componentes que no se incluyen

Desde la 2.0.3, el ejecutable no incluye **Qt Virtual Keyboard** ni **Qt PDF**. `build_exe.py` los excluye del paquete y comprueba la tabla de contenido del build. Qt Virtual Keyboard se ofrece bajo GPLv3 o licencia comercial, no bajo LGPLv3, por lo que no se distribuye.

## Obligaciones de la LGPLv3 (Qt y PySide6)

- Los textos de la LGPLv3 y la GPLv3 se incluyen en `licenses/` y en el ejecutable.
- El código fuente de las versiones usadas es público:
  - Qt 6.12.0: https://download.qt.io/official_releases/qt/6.12/6.12.0/
  - PySide6 6.12.0: https://pypi.org/project/PySide6/6.12.0/
  - Shiboken6 6.12.0: https://pypi.org/project/shiboken6/6.12.0/
  - PySide6 (pyside-setup), etiqueta v6.12.0: https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.12.0
- Se pueden sustituir Qt y PySide6 por versiones modificadas o compatibles y volver a generar el ejecutable con `build_exe.bat`, tras actualizar `requirements.lock` con las versiones usadas.

## Límites conocidos

- No hay SBOM oficial de Qt para el wheel de PySide6 6.12.0. El paquete no lo incluye. Por eso la licencia de cada módulo Qt no está certificada: la licencia se declara por paquete, no por módulo.
- Los módulos de Python empaquetados en el archivo comprimido interno del ejecutable no se listan uno a uno en este documento.
- Las versiones exactas de las bibliotecas nativas que van dentro del runtime de Python (OpenSSL, SQLite, zlib, bzip2, XZ, Zstandard y libffi) no se han verificado en este documento. Sus licencias son las de cada proyecto.
- Este documento describe el cumplimiento técnico del paquete. No es un análisis jurídico.
