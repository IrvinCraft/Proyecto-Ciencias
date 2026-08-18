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
    gh release create v1.0.1 --title "v1.0.1" --notes "Descripcion del cambio"
"""

import json
import logging
import os
import re
import shutil
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
    "questions.csv",
    "questions.json",
    "quiz.log",
    "__pycache__",
    ".git",
    "update_tmp",
    ".~lock.questions.csv#",
}

VERSION = "1.0.0"
USER_AGENT = "Quiz-Educativo-updater/1.0"


class UpdateError(Exception):
    """Error controlado durante la comprobacion o aplicacion de una actualizacion."""


def _parse_version(value):
    """Convierte 'v1.2.3' -> [1, 2, 3] para comparar numericamente."""
    parts = re.findall(r"\d+", str(value))
    nums = [int(p) for p in parts]
    return (nums + [0, 0, 0])[:3]


def _gh_token():
    """Busca el token de GitHub configurado por el CLI 'gh'.

    Necesario cuando el repositorio es PRIVADO (las descargas anonimas dan 404
    en repos privados). Revisa las rutas del CLI de gh en Linux/mac y Windows
    con un mini-parser (sin dependencias). Devuelve una cadena o None.
    """
    candidates = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(os.path.join(appdata, "GitHub CLI", "hosts.yml"))
    else:
        candidates.append(os.path.join(os.path.expanduser("~"), ".config", "gh", "hosts.yml"))

    lines = None
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            break
        except Exception:
            continue
    if lines is None:
        return None

    in_core = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            in_core = stripped.rstrip(":").lower() == "github.com"
            continue
        if in_core and indent == 4 and stripped.startswith("oauth_token:"):
            token = stripped.split(":", 1)[1].strip().strip("'\"")
            if token:
                return token
    return None


def _auth_headers():
    """Cabeceras base; agrega Authorization si hay token de gh."""
    headers = {"User-Agent": USER_AGENT}
    token = _gh_token()
    if token:
        headers["Authorization"] = "Bearer {}".format(token)
    return headers


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

    Usa el token de gh (~/.config/gh/hosts.yml) si existe, necesario para
    repositorios PRIVADOS. Devuelve un dict con 'version', 'tag', 'url'
    (zip a descargar) y 'notas' si existe una version mas nueva que la local,
    o None si la app ya esta al dia (o el repo aun no tiene releases).
    Lanza UpdateError si no hay conexion o GitHub responde con un error.
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
        "notas": str(data.get("body") or "").strip(),
    }


def apply_update(zip_url, new_version):
    """Descarga y aplica la actualizacion.

    Extrae el zip a una carpeta temporal, copia los archivos del proyecto
    sobre la instalacion actual saltando los datos preservados del usuario,
    y limpia los .pyc viejos. Devuelve (nueva_version, mensaje).

    En la version compilada (exe) no se puede sobrescribir el ejecutable en
    marcha; se indica que la actualizacion se descarga desde GitHub Releases.
    """
    if getattr(sys, "frozen", False):
        raise UpdateError(
            "Esta version empaquetada (.exe) se actualiza descargando el "
            "nuevo QuizEducativo.exe desde GitHub Releases"
        )

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