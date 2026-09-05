# Captura de fotos — Intel RealSense D435i

Aplicación web (Flask) para tomar fotos en color (RGB) con la cámara Intel RealSense D435i.

## Requisitos

- Python 3.9 – 3.11 (recomendado; `pyrealsense2` en PyPI todavía no publica ruedas
  oficiales para todas las versiones nuevas de Python, como 3.12/3.13). Si tu
  Python actual no tiene wheel disponible, instala una versión 3.10/3.11 en
  paralelo (por ejemplo con [pyenv-win](https://github.com/pyenv-win/pyenv-win)
  o el instalador oficial) y crea el entorno virtual con esa versión.
- Cámara Intel RealSense D435i conectada por USB 3.0.
- Drivers/SDK de Intel RealSense (librealsense) instalados en el sistema.
  En Windows, instala el **Intel RealSense SDK 2.0** desde:
  https://github.com/IntelRealSense/librealsense/releases

## Instalación

```powershell
cd RealSense_D435i_Capture
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Si `pip install pyrealsense2` falla por falta de wheel para tu versión de
Python, verifica en https://pypi.org/project/pyrealsense2/#files qué
versiones de Python soporta el release actual, o compílalo desde el
código fuente de librealsense.

## Uso

```powershell
python app.py
```

Abre el navegador en http://localhost:5000

- El servidor intenta iniciar la cámara automáticamente al arrancar.
- Botón **Iniciar cámara** / **Detener cámara**: controla el stream manualmente.
- Botón **📸 Tomar foto** (o barra espaciadora): guarda el frame actual en
  la carpeta `capturas/` con nombre `foto_AAAAMMDD_HHMMSS.jpg`.
- La galería lateral muestra las fotos guardadas y permite eliminarlas.

## Estructura

```
RealSense_D435i_Capture/
├── app.py                 # Servidor Flask + manejo del pipeline RealSense
├── requirements.txt
├── templates/index.html
├── static/css/style.css
├── static/js/app.js
└── capturas/               # Fotos guardadas (creada automáticamente)
```

## Notas

- Solo se captura el stream de **color**; no se usa el sensor de profundidad
  en esta versión.
- Si `pyrealsense2` no está instalado o no se detecta la cámara, la interfaz
  sigue funcionando y muestra un aviso claro en el estado, en vez de fallar.
