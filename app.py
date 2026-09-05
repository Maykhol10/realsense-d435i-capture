"""
Sistema de captura de fotos con Intel RealSense D435i (solo color/RGB),
pensado para armar datasets de entrenamiento de reconocimiento de imágenes.

Ejecuta un servidor Flask que:
  - Muestra video en vivo del stream de color de la cámara.
  - Permite tomar una foto (botón o tecla) asignada a una clase/etiqueta,
    guardándola en capturas/<clase>/.
  - Muestra una galería agrupada por clase, con conteo por clase para
    detectar datasets desbalanceados.
  - Permite descargar fotos individuales, por clase (.zip) o todo el
    dataset completo (.zip), preservando la estructura de carpetas.

Requiere el SDK pyrealsense2 (librealsense) y una cámara D435i conectada
por USB 3.
"""

import io
import os
import re
import sys
import threading
import time
import webbrowser
import zipfile
from datetime import datetime

import cv2
import numpy as np
from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    render_template,
    request,
    send_file,
    send_from_directory,
)

try:
    import pyrealsense2 as rs
except ImportError:
    rs = None


def resource_path(relative):
    """Ruta a recursos empaquetados (templates/static), tanto en modo
    script como dentro de un .exe generado con PyInstaller."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def app_dir():
    """Carpeta donde vive el .exe (o el script), para guardar 'capturas'
    junto al programa en vez de en la carpeta temporal de extracción."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = app_dir()
CAPTURES_DIR = os.path.join(BASE_DIR, "capturas")
SIN_CLASE = "sin_clase"
os.makedirs(CAPTURES_DIR, exist_ok=True)

app = Flask(
    __name__,
    template_folder=resource_path("templates"),
    static_folder=resource_path("static"),
)

_CLASE_INVALIDA = re.compile(r"[^a-zA-Z0-9_\-áéíóúÁÉÍÓÚñÑ ]+")


def normalizar_clase(clase):
    """Convierte el nombre de clase escrito por el usuario en un nombre de
    carpeta seguro (sin rutas ni caracteres especiales)."""
    clase = (clase or "").strip()
    if not clase:
        return SIN_CLASE
    clase = _CLASE_INVALIDA.sub("", clase)
    clase = clase.strip().replace(" ", "_")
    return clase[:60] if clase else SIN_CLASE


def ruta_segura(*partes):
    """Resuelve una ruta dentro de CAPTURES_DIR y rechaza cualquier intento
    de salir de esa carpeta (path traversal)."""
    destino = os.path.abspath(os.path.join(CAPTURES_DIR, *partes))
    raiz = os.path.abspath(CAPTURES_DIR)
    if destino != raiz and not destino.startswith(raiz + os.sep):
        abort(400)
    return destino


def listar_dataset():
    """Devuelve {clase: [nombres_de_archivo,...]} ordenado, ignorando
    carpetas/archivos que no sean imágenes."""
    dataset = {}
    for clase in sorted(os.listdir(CAPTURES_DIR)):
        carpeta = os.path.join(CAPTURES_DIR, clase)
        if not os.path.isdir(carpeta):
            continue
        fotos = sorted(
            (f for f in os.listdir(carpeta) if f.lower().endswith((".jpg", ".jpeg", ".png"))),
            reverse=True,
        )
        if fotos:
            dataset[clase] = fotos
    return dataset


class RealSenseCamera:
    """Envoltorio para el pipeline de RealSense, con acceso thread-safe
    al último frame de color capturado."""

    def __init__(self, width=1280, height=720, fps=30):
        self.width = width
        self.height = height
        self.fps = fps
        self.pipeline = None
        self.config = None
        self.webcam = None
        self.fuente = None  # "realsense" o "webcam"
        self.running = False
        self.lock = threading.Lock()
        self.last_frame = None  # numpy array BGR
        self.error = None
        self.thread = None

    def start(self):
        if self.running:
            return True

        if self._iniciar_realsense():
            self.fuente = "realsense"
        elif self._iniciar_webcam():
            self.fuente = "webcam"
        else:
            return False

        self.error = None
        self.running = True
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()
        return True

    def _iniciar_realsense(self):
        if rs is None:
            self.error = (
                "El paquete 'pyrealsense2' no está instalado. "
                "Instálalo con: pip install pyrealsense2"
            )
            return False
        try:
            self.pipeline = rs.pipeline()
            self.config = rs.config()
            self.config.enable_stream(
                rs.stream.color, self.width, self.height, rs.format.bgr8, self.fps
            )
            self.pipeline.start(self.config)
            return True
        except Exception as exc:  # noqa: BLE001
            self.error = f"RealSense no disponible: {exc}"
            self.pipeline = None
            return False

    def _iniciar_webcam(self):
        cam = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cam.isOpened():
            cam.release()
            self.error = (self.error or "") + " | No se encontró ninguna webcam de respaldo."
            return False
        ok, _ = cam.read()
        if not ok:
            cam.release()
            self.error = (self.error or "") + " | La webcam de respaldo no entrega imagen."
            return False
        self.webcam = cam
        return True

    def _update_loop(self):
        while self.running:
            try:
                if self.fuente == "realsense":
                    frames = self.pipeline.wait_for_frames(timeout_ms=5000)
                    color_frame = frames.get_color_frame()
                    if not color_frame:
                        continue
                    image = np.asanyarray(color_frame.get_data())
                else:
                    ok, image = self.webcam.read()
                    if not ok:
                        continue
                with self.lock:
                    self.last_frame = image
            except Exception as exc:  # noqa: BLE001
                self.error = f"Error leyendo frames: {exc}"
                time.sleep(0.5)

    def get_frame(self):
        with self.lock:
            return None if self.last_frame is None else self.last_frame.copy()

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=2)
        if self.pipeline is not None:
            try:
                self.pipeline.stop()
            except Exception:  # noqa: BLE001
                pass
        if self.webcam is not None:
            self.webcam.release()
        self.pipeline = None
        self.webcam = None
        self.fuente = None


camera = RealSenseCamera()


def gen_mjpeg():
    """Generador de frames en formato MJPEG para el <img> de vídeo en vivo."""
    placeholder = _make_placeholder("Sin señal de la cámara")
    while True:
        frame = camera.get_frame()
        if frame is None:
            ok, buffer = cv2.imencode(".jpg", placeholder)
        else:
            ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if ok:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )
        time.sleep(0.03)


def _make_placeholder(text):
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(
        img, text, (30, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2, cv2.LINE_AA
    )
    return img


@app.route("/")
def index():
    dataset = listar_dataset()
    total = sum(len(fotos) for fotos in dataset.values())
    return render_template(
        "index.html",
        dataset=dataset,
        total=total,
        clases=sorted(dataset.keys()),
    )


@app.route("/video_feed")
def video_feed():
    return Response(gen_mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/estado")
def api_estado():
    return jsonify(
        {
            "activa": camera.running,
            "error": camera.error,
            "pyrealsense2_disponible": rs is not None,
            "fuente": camera.fuente,
        }
    )


@app.route("/api/iniciar", methods=["POST"])
def api_iniciar():
    ok = camera.start()
    return jsonify({"ok": ok, "error": camera.error})


@app.route("/api/detener", methods=["POST"])
def api_detener():
    camera.stop()
    return jsonify({"ok": True})


@app.route("/api/clases")
def api_clases():
    dataset = listar_dataset()
    return jsonify(
        {
            "clases": [
                {"nombre": clase, "cantidad": len(fotos)}
                for clase, fotos in sorted(dataset.items())
            ]
        }
    )


@app.route("/api/capturar", methods=["POST"])
def api_capturar():
    frame = camera.get_frame()
    if frame is None:
        return jsonify({"ok": False, "error": "No hay imagen disponible todavía."}), 400

    datos = request.get_json(silent=True) or {}
    clase = normalizar_clase(datos.get("clase"))
    carpeta_clase = ruta_segura(clase)
    os.makedirs(carpeta_clase, exist_ok=True)

    nombre = f"{clase}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}.jpg"
    cv2.imwrite(os.path.join(carpeta_clase, nombre), frame)
    return jsonify(
        {
            "ok": True,
            "archivo": nombre,
            "clase": clase,
            "cantidad_clase": len(os.listdir(carpeta_clase)),
        }
    )


@app.route("/capturas/<clase>/<path:nombre>")
def servir_captura(clase, nombre):
    carpeta = ruta_segura(clase)
    return send_from_directory(carpeta, nombre)


@app.route("/api/descargar/<clase>/<path:nombre>")
def api_descargar(clase, nombre):
    carpeta = ruta_segura(clase)
    ruta = os.path.join(carpeta, nombre)
    if not os.path.isfile(ruta):
        return jsonify({"ok": False, "error": "Archivo no encontrado"}), 404
    return send_from_directory(carpeta, nombre, as_attachment=True)


@app.route("/api/descargar_clase/<clase>")
def api_descargar_clase(clase):
    carpeta = ruta_segura(clase)
    if not os.path.isdir(carpeta):
        return jsonify({"ok": False, "error": "Clase no encontrada"}), 404

    fotos = sorted(f for f in os.listdir(carpeta) if f.lower().endswith((".jpg", ".jpeg", ".png")))
    if not fotos:
        return jsonify({"ok": False, "error": "Esa clase no tiene fotos"}), 400

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre in fotos:
            zf.write(os.path.join(carpeta, nombre), arcname=os.path.join(clase, nombre))
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{clase}.zip",
    )


@app.route("/api/descargar_todas")
def api_descargar_todas():
    dataset = listar_dataset()
    if not dataset:
        return jsonify({"ok": False, "error": "No hay fotos para descargar"}), 400

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for clase, fotos in dataset.items():
            for nombre in fotos:
                zf.write(
                    os.path.join(CAPTURES_DIR, clase, nombre),
                    arcname=os.path.join(clase, nombre),
                )
    buffer.seek(0)

    nombre_zip = f"dataset_realsense_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=nombre_zip,
    )


@app.route("/api/eliminar/<clase>/<path:nombre>", methods=["POST"])
def api_eliminar(clase, nombre):
    carpeta = ruta_segura(clase)
    ruta = os.path.join(carpeta, nombre)
    if os.path.isfile(ruta):
        os.remove(ruta)
        if not os.listdir(carpeta):
            os.rmdir(carpeta)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Archivo no encontrado"}), 404


@app.route("/api/eliminar_clase/<clase>", methods=["POST"])
def api_eliminar_clase(clase):
    carpeta = ruta_segura(clase)
    if not os.path.isdir(carpeta):
        return jsonify({"ok": False, "error": "Clase no encontrada"}), 404
    for f in os.listdir(carpeta):
        os.remove(os.path.join(carpeta, f))
    os.rmdir(carpeta)
    return jsonify({"ok": True})


if __name__ == "__main__":
    camera.start()
    threading.Timer(1.2, lambda: webbrowser.open("http://localhost:5000")).start()
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    finally:
        camera.stop()
