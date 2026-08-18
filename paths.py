"""
paths.py
========
Resuelve las rutas de la aplicacion en modo fuente (python main.py) y en
modo compilado (.exe creado con PyInstaller).

- resource_dir(): datos de SOLO LECTURA de la app (assets/ sonidos, el banco
  de preguntas por defecto). Van dentro del paquete compilado.
- data_dir(): datos ESCRIBIBLES del usuario (config.json, csv/ importado,
  quiz.log). Van a %APPDATA%/QuizEducativo en Windows y ~/.quiz_educativo en
  Linux/macOS para que el programa pueda guardarlos sin permisos especiales.
"""
import os
import sys

APP_NAME = "QuizEducativo"


def is_frozen():
    """True cuando el programa corre como aplicacion compilada (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def resource_dir():
    """Directorio con los recursos empaquetados (solo lectura)."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return meipass
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def data_dir():
    """Directorio ESCRIBIBLE con los datos del usuario, creado si hace falta."""
    if is_frozen():
        if sys.platform == "win32":
            base = os.environ.get("APPDATA") or os.path.expanduser("~")
        else:
            base = os.path.expanduser("~")
        folder = os.path.join(base, "." + APP_NAME) if sys.platform != "win32" else \
            os.path.join(base, APP_NAME)
    else:
        folder = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(folder, exist_ok=True)
    return folder