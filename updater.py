"""
updater.py
==========
Sistema de actualizaciones de la aplicacion via GitHub Releases.

La aplicacion consulta el release mas reciente del repositorio GitHub y,
si hay una version mas nueva que la local, permite descargarla y aplicarla
de forma no destructiva (conserva config.json, csv/ y las preguntas del
usuario). Solo usa la biblioteca estandar de Python (urllib, json,
zipfile, ...), no agregades dependencias.

Como publicar una nueva version (en la PC de desarrollo):
    git add -A
    git commit -m "v1.0.1"
    git tag v1.0.1
    git push origin master --tags

El workflow de GitHub compila el instalador (Inno Setup) y el paquete
update.zip, y los sube al release del tag. La app instalada se actualiza en
sitio descargando update.zip (no se acumulan .exe).
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

logger = logging.getLogger("quiz.updater")

GITHUB_REPO = "IrvinCraft/Proyecto-Ciencias"
GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
RELEASE_URL = "https://github.com/{repo}/archive/refs/tags/{tag}.zip"

# Datos locales del usuario que NUNCA se sobrescriben al actualizar
PRESERVED = {
    "config.json",
    "csv",
    "progress.json",
    "questions.csv",
    "questions.json",
    "quiz.log",
    "__pycache__",
    ".git",
    "update_tmp",
    ".~lock.questions.csv#",
}

VERSION = "1.0.4"
USER_AGENT = "Quiz-Educativo-updater/1.0"


class UpdateError(Exception):
    """Error controlado durante la comprobacion o aplicacion de una actualizacion."""


def _parse_version(value):
    """Convierte 'v1.2.3' -> [1, 2, 3] para comparar numericamente."""
    parts = re.findall(r"\d+", str(value))
    nums = [int(p) for p in parts]
    return (nums + [0, 0, 0])[:3]


def _auth_headers():
    """Cabeceras basicas. El repo es publico, asi que no hace falta token:
    las peticiones son anonimas (evita errores por tokens vencidos)."""
    return {"User-Agent": USER_AGENT}


def _http_get_json(url, timeout=15):
    """GET a una URL y parsea la respuesta como JSON."""
    headers = _auth_headers()
    headers["Accept"] = "application/vnd.github+json"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_download(url, dest, timeout=120):
    """Descarga una URL directamente a un archivo."""
    req = urllib.request.Request(url, headers=_auth_headers())
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)


def check_for_update():
    """Consulta GitHub por el release mas reciente.

    El repo es publico: la consulta es anonima (sin token). Devuelve un dict
    con 'version', 'tag', 'url' (zip a descargar) y 'notas' si existe una
    version mas nueva que la local, o None si la app ya esta al dia (o el repo
    aun no tiene releases). Lanza UpdateError si no hay conexion o GitHub
    responde con un error.
    """
    url = GITHUB_API.format(repo=GITHUB_REPO)
    try:
        data = _http_get_json(url)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            logger.info("El repositorio aun no tiene releases publicadas")
            return None
        raise UpdateError("GitHub respondio con un error HTTP {}".format(exc.code))
    except Exception as exc:
        raise UpdateError("No se pudo contactar a GitHub: {}".format(exc))

    tag = str(data.get("tag_name", "")).strip()
    if not tag:
        return None

    latest = _parse_version(tag)
    if latest <= _parse_version(VERSION):
        return None

    return {
        "version": ".".join(str(n) for n in latest),
        "tag": tag,
        "url": RELEASE_URL.format(repo=GITHUB_REPO, tag=tag),
        # Paquete de la app para actualizacion en sitio (una carpeta onedir).
        # Solo existe en los releases nuevos; None en releases viejos.
        "update_zip": _asset_url(data, "update.zip"),
        "notas": str(data.get("body") or "").strip(),
    }


def _asset_url(data, name):
    """Busca en el release el 'browser_download_url' de un asset por nombre."""
    for asset in data.get("assets") or []:
        if asset.get("name") == name:
            return asset.get("browser_download_url")
    return None


def apply_update(zip_url, new_version):
    """Descarga y aplica la actualizacion.

    - Modo fuente (python main.py): extrae el zip del tag y copia sobre el
      proyecto, preservando los datos del usuario.
    - Modo instalado (.exe): descarga el paquete update.zip (los archivos
      nuevos de la app) y deja un .bat que espera al cierre de la app, pisa
      los archivos de la instalacion y la reabre. Asi NO se acumulan .exe:
      siempre se actualiza la instalacion existente.
    """
    if getattr(sys, "frozen", False):
        return _apply_update_installed(zip_url, new_version)
    return _apply_update_source(zip_url, new_version)


def _apply_update_source(zip_url, new_version):
    """Modo fuente: extrae el zip del tag y copia sobre el proyecto
    saltando los datos preservados del usuario."""
    if not zip_url:
        raise UpdateError("Sin URL de actualizacion")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    tmp = tempfile.mkdtemp(prefix="quiz_update_")
    zip_path = os.path.join(tmp, "update.zip")
    extract_dir = os.path.join(tmp, "extract")
    entries = 0
    try:
        logger.info("Descargando actualizacion %s desde %s", new_version, zip_url)
        _http_download(zip_url, zip_path)

        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            # Seguridad: rechazar rutas absolutas o con '..'
            for name in zf.namelist():
                norm = os.path.normpath(name)
                if norm.startswith(("..", "/")) or os.path.isabs(norm):
                    raise UpdateError("El paquete de actualizacion es invalido")
            zf.extractall(extract_dir)

        # Localizar la carpeta raiz del proyecto dentro del zip
        root_candidates = [
            os.path.join(extract_dir, d)
            for d in os.listdir(extract_dir)
            if os.path.isdir(os.path.join(extract_dir, d))
        ]
        if not root_candidates:
            raise UpdateError("El paquete de actualizacion no contiene el proyecto")
        src = root_candidates[0]

        # Limpiar bytecode viejo antes de copiar
        shutil.rmtree(os.path.join(base_dir, "__pycache__"), ignore_errors=True)

        for name in os.listdir(src):
            if name in PRESERVED:
                logger.info("Preservando (no se sobrescribe): %s", name)
                continue
            s = os.path.join(src, name)
            d = os.path.join(base_dir, name)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copy2(s, d)
            entries += 1

        logger.info("Actualizacion aplicada: %d entradas copiadas", entries)
        return new_version, (
            "Actualizacion instalada correctamente. Reinicia la aplicacion "
            "para aplicar los cambios."
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _winpath(path):
    """Normaliza una ruta a uso en .bat de Windows (barras invertidas)."""
    return os.path.normpath(path).replace(os.sep, "\\") if os.sep != "\\" \
        else os.path.normpath(path)


def _write_update_bat(bat_path, extract_dir, install_dir, tmp_dir):
    """Genera el .bat que aplica la actualizacion en la instalacion:
    espera a que cierre la app, reemplaza los archivos y la reabre."""
    exe = _winpath(os.path.join(install_dir, "QuizEducativo.exe"))
    extract = _winpath(extract_dir)
    install = _winpath(install_dir)
    tmp = _winpath(tmp_dir)
    lines = [
        "@echo off",
        "rem Aplicador de actualizacion generado por la app",
        "timeout /t 3 /nobreak >nul",
        "taskkill /IM QuizEducativo.exe /F >nul 2>&1",
        'xcopy "{extract}" "{install}" /E /Y /I >nul'.format(
            extract=extract, install=install
        ),
        'rmdir /s /q "{tmp}" >nul 2>&1'.format(tmp=tmp),
        'start "" "{exe}"'.format(exe=exe),
    ]
    with open(bat_path, "w", encoding="utf-8", newline="") as fh:
        # newline='' : sin traducciones, el \r\n va literal (evita dobles \r)
        fh.write("\r\n".join(lines) + "\r\n")


def _apply_update_installed(zip_url, new_version):
    """Modo instalado (.exe): descarga update.zip y programa el reemplazo.

    No se puede pisar el .exe en marcha, asi que se escribe un .bat que
    cierra la app, sustituye los archivos de la instalacion y la reabre.
    """
    if not zip_url:
        raise UpdateError(
            "El release no trae el paquete de actualizacion (update.zip). "
            "Descarga el instalador desde GitHub Releases."
        )

    install_dir = os.path.dirname(os.path.abspath(sys.executable))
    tmp = tempfile.mkdtemp(prefix="quiz_update_")
    zip_path = os.path.join(tmp, "update.zip")
    extract_dir = os.path.join(tmp, "extract")

    logger.info("Descargando paquete de actualizacion %s desde %s",
                new_version, zip_url)
    _http_download(zip_url, zip_path)

    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            norm = os.path.normpath(name)
            if norm.startswith(("..", "/")) or os.path.isabs(norm):
                raise UpdateError("El paquete de actualizacion es invalido")
        zf.extractall(extract_dir)

    bat_path = os.path.join(tmp, "apply_update.bat")
    _write_update_bat(bat_path, extract_dir, install_dir, tmp)

    # Lanzar el .bat en una ventana nueva y salir; el bat borra tmp al final,
    # por eso aqui NO se limpia la carpeta temporal.
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(["cmd", "/c", bat_path], creationflags=flags)
    return new_version, (
        "La app se cerrara y se actualizara sola. Vuelve a abrirla en unos "
        "segundos."
    )