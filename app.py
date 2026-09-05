"""
Sistema de captura de fotos con Intel RealSense D435i (solo color/RGB).

Ejecuta un servidor Flask que:
  - Muestra video en vivo del stream de color de la cámara.
  - Permite tomar una foto (botón o tecla) y guardarla en /capturas.
  - Muestra una galería de las fotos ya tomadas.

Requiere el SDK pyrealsense2 (librealsense) y una cámara D435i conectada
por USB 3.
"""

import io
import os
import threading
import time
import zipfile
from datetime import datetime

import cv2
import numpy as np
from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    send_file,
    send_from_directory,
    url_for,
)

try:
    import pyrealsense2 as rs
except ImportError:
    rs = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTURES_DIR = os.path.join(BASE_DIR, "capturas")
os.makedirs(CAPTURES_DIR, exist_ok=True)

app = Flask(__name__)


class RealSenseCamera:
    """Envoltorio para el pipeline de RealSense, con acceso thread-safe
    al último frame de color capturado."""

    def __init__(self, width=1280, height=720, fps=30):
        self.width = width
        self.height = height
        self.fps = fps
        self.pipeline = None
        self.config = None
        self.running = False
        self.lock = threading.Lock()
        self.last_frame = None  # numpy array BGR
        self.error = None
        self.thread = None

    def start(self):
        if rs is None:
            self.error = (
                "El paquete 'pyrealsense2' no está instalado. "
                "Instálalo con: pip install pyrealsense2"
            )
            return False
        if self.running:
            return True
        try:
            self.pipeline = rs.pipeline()
            self.config = rs.config()
            self.config.enable_stream(
                rs.stream.color, self.width, self.height, rs.format.bgr8, self.fps
            )
            self.pipeline.start(self.config)
        except Exception as exc:  # noqa: BLE001
            self.error = f"No se pudo iniciar la cámara: {exc}"
            self.pipeline = None
            return False

        self.error = None
        self.running = True
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()
        return True

    def _update_loop(self):
        while self.running:
            try:
                frames = self.pipeline.wait_for_frames(timeout_ms=5000)
                color_frame = frames.get_color_frame()
                if not color_frame:
                    continue
                image = np.asanyarray(color_frame.get_data())
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
        self.pipeline = None


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
    fotos = sorted(os.listdir(CAPTURES_DIR), reverse=True)
    return render_template("index.html", fotos=fotos, camara_activa=camera.running)


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


@app.route("/api/capturar", methods=["POST"])
def api_capturar():
    frame = camera.get_frame()
    if frame is None:
        return jsonify({"ok": False, "error": "No hay imagen disponible todavía."}), 400

    nombre = f"foto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    ruta = os.path.join(CAPTURES_DIR, nombre)
    cv2.imwrite(ruta, frame)
    return jsonify({"ok": True, "archivo": nombre})


@app.route("/capturas/<path:nombre>")
def servir_captura(nombre):
    return send_from_directory(CAPTURES_DIR, nombre)


@app.route("/api/descargar/<path:nombre>")
def api_descargar(nombre):
    ruta = os.path.join(CAPTURES_DIR, nombre)
    if not os.path.isfile(ruta) or os.path.dirname(ruta) != CAPTURES_DIR:
        return jsonify({"ok": False, "error": "Archivo no encontrado"}), 404
    return send_from_directory(CAPTURES_DIR, nombre, as_attachment=True)


@app.route("/api/descargar_todas")
def api_descargar_todas():
    fotos = sorted(
        f for f in os.listdir(CAPTURES_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png"))
    )
    if not fotos:
        return jsonify({"ok": False, "error": "No hay fotos para descargar"}), 400

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre in fotos:
            zf.write(os.path.join(CAPTURES_DIR, nombre), arcname=nombre)
    buffer.seek(0)

    nombre_zip = f"capturas_realsense_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=nombre_zip,
    )


@app.route("/api/eliminar/<path:nombre>", methods=["POST"])
def api_eliminar(nombre):
    ruta = os.path.join(CAPTURES_DIR, nombre)
    if os.path.isfile(ruta) and os.path.dirname(ruta) == CAPTURES_DIR:
        os.remove(ruta)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Archivo no encontrado"}), 404


if __name__ == "__main__":
    camera.start()
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    finally:
        camera.stop()
