"""
settings.py
===========
Gestiona la configuracion del quiz (carga, guarda, restaura valores por defecto).
No depende de Pygame; se puede usar de forma aislada.
"""
import json
import os
import logging

from quiz_logic import VALID_LEVELS

logger = logging.getLogger("quiz.settings")

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config.json"
)

DEFAULTS = {
    "num_questions": 10,
    "levels": ["facil", "media", "dificil", "ultra_dificil"],
    "points": {
        "facil": 10,
        "media": 20,
        "dificil": 30,
        "ultra_dificil": 50,
    },
    "time_per_question": 15,
    "unlimited_time": False,
    "question_file": "questions.csv",
}


class Settings:
    """Contenedor de configuracion con carga/guarda desde JSON."""

    def __init__(self, filepath: str = DEFAULT_CONFIG_PATH):
        self.filepath = filepath
        self.config = self._deep_copy_defaults()
        self.load()

    def _deep_copy_defaults(self) -> dict:
        """Copia profunda de los valores por defecto (sin mutar DEFAULTS)."""
        return {
            "num_questions": DEFAULTS["num_questions"],
            "levels": list(DEFAULTS["levels"]),
            "points": dict(DEFAULTS["points"]),
            "time_per_question": DEFAULTS["time_per_question"],
            "unlimited_time": DEFAULTS["unlimited_time"],
            "question_file": DEFAULTS["question_file"],
        }

    # -- carga / guarda ------------------------------------------------------
    def load(self):
        """Carga config.json si existe; si no, usa valores por defecto."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Fundir con defaults para no perder claves nuevas
                self._merge(data)
                logger.info("Config cargada desde %s", self.filepath)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("config.json corrupto (%s); usando valores por defecto", e)
                # Si el archivo esta corrupto, usar defaults
                self.config = self._deep_copy_defaults()
        else:
            logger.info("No existe %s; usando valores por defecto", self.filepath)
            self.config = self._deep_copy_defaults()

    def _merge(self, data: dict):
        """Une data parcial conservando estructura de defaults (sin mutarlos)."""
        cfg = self._deep_copy_defaults()
        for key in DEFAULTS:
            if key in data:
                if isinstance(DEFAULTS[key], dict) and isinstance(data[key], dict):
                    for sub in cfg[key]:
                        if sub in data[key]:
                            cfg[key][sub] = data[key][sub]
                elif isinstance(DEFAULTS[key], list) and isinstance(data[key], list):
                    cfg[key] = [
                        v for v in data[key]
                        if v in VALID_LEVELS
                    ] or list(DEFAULTS[key])
                else:
                    cfg[key] = data[key]
        self.config = cfg

    def save(self):
        """Guarda la configuracion actual en config.json."""
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)
        logger.info("Config guardada en %s: %s", self.filepath, self.config)

    def restore_defaults(self):
        """Restaura todos los valores por defecto."""
        self.config = self._deep_copy_defaults()

    # -- validacion ----------------------------------------------------------
    def validate(self) -> list:
        """Valida la configuracion. Devuelve lista de errores (vacia si OK)."""
        errors = []
        nq = self.config.get("num_questions", 0)
        if not isinstance(nq, int) or nq < 4 or nq > 100:
            errors.append("num_questions debe ser entero entre 4 y 100")

        pts = self.config.get("points", {})
        for lvl in DEFAULTS["points"]:
            val = pts.get(lvl)
            if not isinstance(val, (int, float)) or val < 0:
                errors.append(f"Puntos '{lvl}' invalidos")

        t = self.config.get("time_per_question")
        if not isinstance(t, (int, float)) or t <= 0:
            errors.append("time_per_question debe ser positivo")

        levels = self.config.get("levels", [])
        if not isinstance(levels, list) or not levels:
            errors.append("levels debe incluir al menos un nivel")
        else:
            for lvl in levels:
                if lvl not in VALID_LEVELS:
                    errors.append(f"Nivel desconocido en config: {lvl}")

        return errors

    @property
    def as_dict(self) -> dict:
        """Devuelve la config como diccionario para pasar a Quiz."""
        return dict(self.config)

    # -- acceso comodo -------------------------------------------------------
    @property
    def num_questions(self) -> int:
        return self.config["num_questions"]

    @num_questions.setter
    def num_questions(self, val: int):
        self.config["num_questions"] = int(val)

    @property
    def points(self) -> dict:
        return self.config["points"]

    @property
    def time_per_question(self) -> float:
        return self.config["time_per_question"]

    @time_per_question.setter
    def time_per_question(self, val: float):
        self.config["time_per_question"] = float(val)

    @property
    def unlimited_time(self) -> bool:
        return self.config.get("unlimited_time", False)

    @unlimited_time.setter
    def unlimited_time(self, val: bool):
        self.config["unlimited_time"] = bool(val)

    @property
    def question_file(self) -> str:
        return self.config.get("question_file", "questions.csv")

    @question_file.setter
    def question_file(self, val: str):
        self.config["question_file"] = str(val)

    @property
    def levels(self) -> list:
        return list(self.config.get("levels", list(VALID_LEVELS)))

    @levels.setter
    def levels(self, vals: list):
        valid = [v for v in vals if v in VALID_LEVELS]
        self.config["levels"] = valid if valid else list(VALID_LEVELS)
