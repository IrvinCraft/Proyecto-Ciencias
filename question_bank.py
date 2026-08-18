"""
question_bank.py
================
Gestiona el banco de preguntas importado.

Cada importacion se copia a una subcarpeta con la fecha/hora como nombre:

    csv/2026-08-13_14-30-00/preguntas_ciencias.csv

Lista las "sesiones anteriores" leyendo csv/ y validando cada archivo.
No depende de Pygame; se puede usar de forma aislada.
"""
import os
import shutil
import logging
from datetime import datetime

from quiz_logic import QuestionLoader
from paths import data_dir

logger = logging.getLogger("quiz.bank")

BANK_DIR = os.path.join(data_dir(), "csv")


def ensure_bank_dir():
    """Crea la carpeta csv/ en la raiz si no existe."""
    os.makedirs(BANK_DIR, exist_ok=True)


def import_csv_to_bank(src_path: str) -> str:
    """Copia (sin mover) un CSV a csv/<YYYY-MM-DD_HH-MM-SS>/<nombre original>.

    Devuelve la ruta final de la copia.
    """
    ensure_bank_dir()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest_dir = os.path.join(BANK_DIR, timestamp)
    os.makedirs(dest_dir, exist_ok=True)
    name = os.path.basename(src_path).strip() or "preguntas.csv"
    dest = os.path.join(dest_dir, name)
    shutil.copy2(src_path, dest)
    logger.info("CSV copiado a %s", dest)
    return dest


def _parse_session_date(folder_name: str):
    """Convierte 'YYYY-MM-DD_HH-MM-SS' a (datetime, etiqueta legible)."""
    try:
        dt = datetime.strptime(folder_name, "%Y-%m-%d_%H-%M-%S")
        return dt, dt.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return None, folder_name


def _describe_session(folder_name: str, file_path: str) -> dict:
    """Construye el dict de una sesion, validando el CSV guardado."""
    dt, date_label = _parse_session_date(folder_name)
    valid = True
    count = None
    error = None
    try:
        questions, _ = QuestionLoader.load_lenient(file_path)
        count = len(questions)
    except Exception as e:
        valid = False
        error = str(e)
    return {
        "folder": folder_name,
        "path": file_path,
        "filename": os.path.basename(file_path),
        "date": dt,
        "date_label": date_label,
        "num_questions": count,
        "valid": valid,
        "error": error,
    }


def list_sessions() -> list:
    """Lista todas las sesiones importadas, mas recientes primero."""
    sessions = []
    if not os.path.isdir(BANK_DIR):
        return sessions
    for folder_name in sorted(os.listdir(BANK_DIR), reverse=True):
        folder_path = os.path.join(BANK_DIR, folder_name)
        if not os.path.isdir(folder_path):
            continue
        for fname in sorted(os.listdir(folder_path)):
            if fname.lower().endswith(".csv"):
                sessions.append(
                    _describe_session(folder_name, os.path.join(folder_path, fname))
                )
    # Las carpetas sin fecha (no parseables) van al final
    sessions.sort(
        key=lambda s: (s["date"] is None, s["date"] if s["date"] else datetime.min),
        reverse=True,
    )
    return sessions
