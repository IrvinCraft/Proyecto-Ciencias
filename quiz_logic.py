"""
quiz_logic.py
=============
Lógica del juego separada de la interfaz gráfica.
Contiene: Question, QuestionLoader, Quiz
No depende de Pygame; se puede probar de forma aislada.
"""
import json
import csv
import random
import os
import io
import re
import unicodedata
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger("quiz.logic")


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
VALID_LEVELS = ("facil", "media", "dificil", "ultra_dificil")

# Nombres canonicos de las columnas de un CSV de preguntas
OPCION_COLS = ("opcion_a", "opcion_b", "opcion_c", "opcion_d")

# Sinonimos aceptados por columna (ademas de las variaciones de escritura).
# Excel en espanol a veces llama a la respuesta 'Clave de respuesta correcta'.
COLUMN_ALIASES = {
    "respuesta_correcta": (
        "respuesta_correcta", "clave_de_respuesta", "clave_de_respuesta_correcta",
        "clave_respuesta", "respuesta", "resp_correcta", "clave", "correcta",
        "answer", "respuesta_ok",
    ),
    "nivel": ("nivel", "dificultad", "dificultad_del_item"),
}

# Sinonimos de los VALORES de nivel (despues de normalizar tildes/case)
NIVEL_ALIASES = {
    "medio": "media",
    "baja_dificultad": "facil",
    "alta_dificultad": "dificil",
}


# ---------------------------------------------------------------------------
# Question
# ---------------------------------------------------------------------------
@dataclass
class Question:
    """Representa una pregunta del banco."""
    texto: str
    opciones: List[str]          # 4 opciones (A, B, C, D)
    respuesta_correcta: str      # texto exacto de la opción correcta
    nivel: str                   # facil | media | dificil | ultra_dificil

    def __post_init__(self):
        self.nivel = self.nivel.strip().lower()
        if self.nivel not in VALID_LEVELS:
            raise ValueError(f"Nivel desconocido: {self.nivel}")

    @classmethod
    def from_dict(cls, data: dict) -> "Question":
        """Crea una Question a partir de un diccionario (formato JSON)."""
        required = ["pregunta", "opciones", "respuesta_correcta", "nivel"]
        for key in required:
            if key not in data:
                raise ValueError(
                    f"Falta la clave '{key}' en: {data.get('pregunta', '?')}"
                )

        opciones = data["opciones"]
        if not isinstance(opciones, list):
            raise ValueError(f"'opciones' debe ser lista en: {data['pregunta']}")
        if len(opciones) != 4:
            raise ValueError(f"Se requieren 4 opciones en: {data['pregunta']}")

        respuesta = data["respuesta_correcta"]
        if respuesta not in opciones:
            raise ValueError(
                f"Respuesta '{respuesta}' no está en opciones de: {data['pregunta']}"
            )
        return cls(
            texto=data["pregunta"],
            opciones=list(opciones),
            respuesta_correcta=respuesta,
            nivel=data["nivel"],
        )

    def indice_correcto(self) -> int:
        """Devuelve el índice (0-3) de la opción correcta."""
        return self.opciones.index(self.respuesta_correcta)

    def is_correct(self, opcion_elegida: str) -> bool:
        """Verifica si la opción elegida es correcta."""
        return opcion_elegida == self.respuesta_correcta


# ---------------------------------------------------------------------------
# QuestionLoader
# ---------------------------------------------------------------------------
class QuestionLoader:
    """Carga preguntas desde archivos JSON o CSV."""

    @staticmethod
    def load(filepath: str) -> List[Question]:
        """Detecta el formato por extensión y delega."""
        if not os.path.exists(filepath):
            logger.error("No existe el archivo de preguntas: %s", filepath)
            raise FileNotFoundError(f"No se encontro: {filepath}")

        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".json":
            qs = QuestionLoader._load_json(filepath)
        elif ext == ".csv":
            qs = QuestionLoader._load_csv(filepath)
        else:
            raise ValueError(f"Formato no soportado: {ext}. Use .json o .csv")
        logger.info("Cargadas %d preguntas desde %s", len(qs), filepath)
        return qs

    @staticmethod
    def _load_json(filepath: str) -> List[Question]:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            raw_qs = data.get("questions", data.get("preguntas", []))
        else:
            raw_qs = data

        if not isinstance(raw_qs, list):
            raise ValueError("'questions' debe ser una lista")

        questions: List[Question] = []
        for i, item in enumerate(raw_qs):
            try:
                questions.append(Question.from_dict(item))
            except (ValueError, KeyError) as e:
                raise ValueError(f"Error en pregunta {i + 1}: {e}")
        return questions

    @staticmethod
    def _read_csv_text(filepath: str) -> str:
        """Lee un CSV probando varias codificaciones.

        Un archivo puede estar en utf-8, cp1252 o latin-1 segun con que editor
        lo escribio el autor (Word/Excel en Windows usan cp1252/latin-1 y rompen
        la decodificacion utf-8 con tildes: e.g. byte 0xf3 = 'o' acentuada).
        latin-1 decodifica cualquier byte, asi que siempre hay un fallback.
        """
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                with open(filepath, "r", encoding=enc, newline="") as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        raise ValueError(
            "No se pudo decodificar el CSV (probado utf-8, cp1252 y latin-1)"
        )

    @staticmethod
    def _normalize_header(name: str) -> str:
        """Normaliza un encabezado para aceptar variantes de escritura.

        'Opcion B', 'OPCION B', 'opcion_b', 'oPciON_B', 'opción b' -> 'opcion_b'.
        Baja mayusculas, quita tildes y cambia espacios/signos por guion bajo.
        """
        name = unicodedata.normalize("NFKD", name or "")
        name = name.encode("ascii", "ignore").decode("ascii")
        name = name.strip().lower()
        return re.sub(r"[^a-z0-9]+", "_", name).strip("_")

    @staticmethod
    def _csv_reader(text: str):
        """Devuelve csv.DictReader sobre el texto, detectando el delimitador.

        Excel espanol exporta con punto y coma (';') en vez de coma. Se elige
        el delimitador con mas ocurrencias en la primera linea (coma, ';' o tab).
        """
        first_line = (text.splitlines() or [""])[0]
        delim, best = ",", -1
        for d in (",", ";", "\t"):
            c = first_line.count(d)
            if c > best:
                best, delim = c, d
        return csv.DictReader(io.StringIO(text), delimiter=delim)

    @staticmethod
    def _column_map(fieldnames) -> dict:
        """Mapa clave_canonica -> encabezado original del CSV.

        Resuelve las variaciones de escritura ('Opcion B', 'oPciON_B',
        'opción b') y los sinonimos de la respuesta ('Clave de respuesta
        correcta', 'respuesta', ...) al nombre canonico interno.
        """
        norm2orig: dict = {}
        for header in fieldnames or []:
            norm2orig.setdefault(QuestionLoader._normalize_header(header), header)

        canons = ["pregunta"] + list(OPCION_COLS) + ["respuesta_correcta", "nivel"]
        colmap: dict = {}
        for canon in canons:
            for alias in COLUMN_ALIASES.get(canon, (canon,)):
                if alias in norm2orig:
                    colmap[canon] = norm2orig[alias]
                    break
        return colmap

    @staticmethod
    def _load_csv(filepath: str) -> List[Question]:
        """Carga preguntas desde CSV.
        Columnas: pregunta, opcion_a..d, respuesta_correcta, nivel
        respuesta_correcta indica la letra (A, B, C o D) de la opcion valida.
        Tolerante a codificacion y a variantes en los nombres de columna.
        """
        questions: List[Question] = []
        opcion_cols = list(OPCION_COLS)
        text = QuestionLoader._read_csv_text(filepath)
        reader = QuestionLoader._csv_reader(text)
        colmap = QuestionLoader._column_map(reader.fieldnames)
        required_cols = {"pregunta", "respuesta_correcta", "nivel"}
        missing = required_cols - set(colmap)
        if missing:
            raise ValueError(
                f"Columnas faltantes en CSV: {missing} "
                f"(encabezados encontrados: {sorted(colmap) or 'ninguno'})"
            )

        if set(opcion_cols) - set(colmap):
            raise ValueError(
                f"CSV necesita 4 columnas de opciones: {', '.join(opcion_cols)}"
            )

        def _val(row, key):
            return (row.get(colmap[key]) or "") if key in colmap else ""

        # El nivel puede venir con tildes/case/vocablo variado
        def _nivel(row):
            n = QuestionLoader._normalize_header(_val(row, "nivel"))
            return NIVEL_ALIASES.get(n, n)

        def _respuesta_letra(opciones, respuesta):
            """Convierte la respuesta a una letra A-D. Acepta la letra o el
            texto de la opcion ('b', 'B', 'animales', 'Opción B'...)."""
            if respuesta.upper() in "ABCD":
                return respuesta.upper()
            coincidencias = [
                i for i, o in enumerate(opciones)
                if o and QuestionLoader._normalize_header(o) ==
                QuestionLoader._normalize_header(respuesta)
            ]
            if coincidencias:
                return "ABCD"[coincidencias[0]]
            raise ValueError(
                f"respuesta_correcta debe ser A, B, C o D (o el texto de la "
                f"opcion; se obtuvo '{respuesta}')"
            )

        for i, row in enumerate(reader):
            opciones = [_val(row, c) for c in opcion_cols]
            data = {
                "pregunta": _val(row, "pregunta"),
                "opciones": opciones,
                "respuesta_correcta": opciones["ABCD".index(
                    _respuesta_letra(opciones, _val(row, "respuesta_correcta"))
                )],
                "nivel": _nivel(row),
            }
            try:
                questions.append(Question.from_dict(data))
            except (ValueError, KeyError) as e:
                raise ValueError(f"Error en fila {i + 2}: {e}")
        return questions

    @staticmethod
    def load_lenient(filepath: str):
        """Carga un CSV tolerando filas mal formadas.

        Devuelve una tupla (preguntas_validas, filas_ignoradas).
        Lanza ValueError si las columnas requeridas faltan o si no hay
        ninguna fila valida.
        """
        if not os.path.exists(filepath):
            logger.error("No existe el archivo de preguntas: %s", filepath)
            raise FileNotFoundError(f"No se encontro: {filepath}")

        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".csv":
            return QuestionLoader._load_csv_lenient(filepath)
        questions = QuestionLoader.load(filepath)  # JSON estricto (no salta filas)
        return questions, 0

    @staticmethod
    def _load_csv_lenient(filepath: str):
        """Lee un CSV contando las filas validas e ignorando las malformadas.
        Tolerante a codificacion (utf-8/cp1252/latin-1) y a variantes en los
        encabezados: 'Opcion B', 'OPCION B', 'opcion_b', 'opción b', etc.
        """
        questions: List[Question] = []
        skipped = 0
        opcion_cols = list(OPCION_COLS)
        text = QuestionLoader._read_csv_text(filepath)
        reader = QuestionLoader._csv_reader(text)
        colmap = QuestionLoader._column_map(reader.fieldnames)
        missing = {"pregunta", "respuesta_correcta", "nivel"} - set(colmap)
        if missing:
            raise ValueError(
                f"Columnas faltantes en CSV: {missing} "
                f"(encabezados encontrados: {sorted(colmap) or 'ninguno'})"
            )
        if set(opcion_cols) - set(colmap):
            raise ValueError(
                f"CSV necesita 4 columnas de opciones: {', '.join(opcion_cols)} "
                f"(faltan: {', '.join(sorted(set(opcion_cols) - set(colmap)))})"
            )

        def _val(row, key):
            return (row.get(colmap[key]) or "") if key in colmap else ""

        # El nivel puede venir con tildes/case/vocablo variado
        def _nivel(row):
            n = QuestionLoader._normalize_header(_val(row, "nivel"))
            return NIVEL_ALIASES.get(n, n)

        def _respuesta_letra(opciones, respuesta):
            """Convierte la respuesta a una letra A-D. Acepta la letra o el
            texto de la opcion ('b', 'B', 'animales', 'Opción B'...)."""
            if respuesta.upper() in "ABCD":
                return respuesta.upper()
            coincidencias = [
                i for i, o in enumerate(opciones)
                if o and QuestionLoader._normalize_header(o) ==
                QuestionLoader._normalize_header(respuesta)
            ]
            if coincidencias:
                return "ABCD"[coincidencias[0]]
            raise ValueError(
                f"respuesta_correcta debe ser A, B, C o D (o el texto de la "
                f"opcion; se obtuvo '{respuesta}')"
            )

        for row in reader:
            try:
                pregunta = _val(row, "pregunta").strip()
                if not pregunta:
                    raise ValueError("pregunta vacia")
                opciones = [_val(row, c).strip() for c in opcion_cols]
                data = {
                    "pregunta": pregunta,
                    "opciones": opciones,
                    "respuesta_correcta": opciones["ABCD".index(
                        _respuesta_letra(opciones, _val(row, "respuesta_correcta"))
                    )],
                    "nivel": _nivel(row),
                }
                questions.append(Question.from_dict(data))
            except (ValueError, KeyError, IndexError) as e:
                skipped += 1
                # Modo debug: cada fila rechazada con su numero de linea,
                # un preview de la pregunta y el motivo exacto.
                preview = (_val(row, "pregunta").strip() or "<?>")[:40]
                logger.debug(
                    "Fila %d ignorada [%s]: %s",
                    reader.line_num, preview, e,
                )

        if not questions:
            raise ValueError(
                f"No hay filas validas en el CSV (se ignoraron {skipped} filas)"
            )

        if skipped:
            logger.warning(
                "CSV '%s': %d validas y %d filas ignoradas. "
                "Usa --debug para ver el motivo de cada fila.",
                filepath, len(questions), skipped,
            )
        else:
            logger.debug("CSV '%s': %d preguntas validas.", filepath, len(questions))
        logger.info("Cargadas %d preguntas (lenient) desde %s [ignoradas=%d]",
                    len(questions), filepath, skipped)
        return questions, skipped


# ---------------------------------------------------------------------------
# Quiz (estado del juego)
# ---------------------------------------------------------------------------
class Quiz:
    """Administra el estado del juego: selección, puntuación, cronómetro."""

    def __init__(self, all_questions: List[Question], settings: dict):
        self.all_questions = all_questions
        self.num_questions: int = settings["num_questions"]
        self.points_config: dict = settings["points"]
        self.time_per_question: float = settings["time_per_question"]
        self.unlimited_time: bool = settings.get("unlimited_time", False)

        # Validar cantidad disponible
        if len(all_questions) < self.num_questions:
            self.num_questions = len(all_questions)

        # Distribuir preguntas por nivel
        self.questions: List[Question] = self._distribute_questions()

        # Estado del juego
        self.current_index = 0
        self.score = 0
        self.time_remaining: Optional[float] = (
            self.time_per_question if not self.unlimited_time else None
        )
        self.question_time = 0.0      # segundos transcurridos en la pregunta actual
        self.total_time_used = 0.0
        self.times_responded: List[float] = []   # tiempo por cada pregunta respondida
        self.answer_result: Optional[dict] = None
        self.game_over = False

        # Estadisticas por nivel
        self.stats = {
            lvl: {"correctas": 0, "incorrectas": 0} for lvl in VALID_LEVELS
        }

        # Racha de aciertos consecutivos (para el indicador de la UI)
        self.current_streak = 0
        self.max_streak = 0

    # -- seleccion de preguntas ----------------------------------------------
    def _distribute_questions(self) -> List[Question]:
        """Distribuye preguntas aproximadamente uniforme entre los niveles
        que tienen preguntas disponibles (puede ser un subconjunto)."""
        by_level: dict = {lvl: [] for lvl in VALID_LEVELS}
        for q in self.all_questions:
            by_level[q.nivel].append(q)
        for lvl in by_level:
            random.shuffle(by_level[lvl])

        selected: List[Question] = []
        levels_present = [lvl for lvl in VALID_LEVELS if by_level[lvl]]
        if not levels_present:
            return selected

        per_level = self.num_questions // len(levels_present)
        remainder = self.num_questions % len(levels_present)

        for idx, lvl in enumerate(levels_present):
            take = per_level + (1 if idx < remainder else 0)
            available = by_level[lvl]
            if take <= len(available):
                selected.extend(available[:take])
            else:
                selected.extend(available)

        # Rellenar del pool general si falta
        if len(selected) < self.num_questions:
            pool = [q for q in self.all_questions if q not in selected]
            random.shuffle(pool)
            needed = self.num_questions - len(selected)
            selected.extend(pool[:needed])

        random.shuffle(selected)
        return selected

    # -- estado de juego ------------------------------------------------------
    @property
    def current_question(self) -> Question:
        return self.questions[self.current_index]

    @property
    def question_number(self) -> int:
        return self.current_index + 1

    def answer(self, opcion_elegida: str, time_used: float) -> bool:
        """Procesa una respuesta. time_used = segundos que tardo en responder."""
        q = self.current_question
        correct = q.is_correct(opcion_elegida)
        points = self.points_config[q.nivel] if correct else 0

        self.score += points
        self.total_time_used += time_used
        self.times_responded.append(time_used)

        self.stats[q.nivel]["correctas" if correct else "incorrectas"] += 1

        # Racha de aciertos consecutivos
        if correct:
            self.current_streak += 1
            if self.current_streak > self.max_streak:
                self.max_streak = self.current_streak
        else:
            self.current_streak = 0

        self.answer_result = {
            "correcta": correct,
            "respuesta_elegida": opcion_elegida,
            "respuesta_correcta": q.respuesta_correcta,
            "puntos_obtenidos": points,
            "tiempo_usado": round(time_used, 2),
            "nivel": q.nivel,
        }
        return correct

    def time_out(self, time_used: float):
        """Se acabo el tiempo: cuenta como incorrecta."""
        q = self.current_question
        self.stats[q.nivel]["incorrectas"] += 1
        self.current_streak = 0  # el tiempo agotado corta la racha
        self.total_time_used += time_used
        self.times_responded.append(time_used)
        self.answer_result = {
            "correcta": False,
            "respuesta_elegida": None,
            "respuesta_correcta": q.respuesta_correcta,
            "puntos_obtenidos": 0,
            "tiempo_usado": round(time_used, 2),
            "nivel": q.nivel,
            "timeout": True,
        }

    def next_question(self):
        """Avanza a la siguiente pregunta o termina el juego."""
        self.answer_result = None
        self.current_index += 1
        if self.current_index >= self.num_questions:
            self.game_over = True
        else:
            self.time_remaining = (
                self.time_per_question if not self.unlimited_time else None
            )
            self.question_time = 0.0

    def update_timer(self, dt: float):
        """Actualiza el cronometro. dt en segundos.
        El cronometro queda detenido en cuanto el jugador responde
        (answer_result no es None): el tiempo usado se congela en la pregunta."""
        if self.game_over or self.answer_result is not None:
            return
        self.question_time += dt
        if self.unlimited_time or self.time_remaining is None:
            return
        if self.time_remaining <= dt:
            # Se agoto el tiempo en este frame
            self.time_remaining = 0.0
            self.time_out(self.time_per_question)
        else:
            self.time_remaining -= dt

    def get_summary(self) -> dict:
        """Devuelve el resumen final para la pantalla de resultados."""
        total_correct = sum(
            s["correctas"] for s in self.stats.values()
        )
        total_incorrect = sum(
            s["incorrectas"] for s in self.stats.values()
        )
        responded = len(self.times_responded)
        tiempo_promedio = (
            round(sum(self.times_responded) / responded, 2) if responded else 0.0
        )
        return {
            "score": self.score,
            "total_time": round(self.total_time_used, 2),
            "tiempo_promedio": tiempo_promedio,
            "correctas": total_correct,
            "incorrectas": total_incorrect,
            "num_questions": self.num_questions,
            "max_streak": self.max_streak,
            "stats": dict(self.stats),
        }


# ---------------------------------------------------------------------------
# Persistencia de progreso (reanudar un quiz a medio terminar)
# ---------------------------------------------------------------------------
PROGRESS_VERSION = 1


def save_progress(filepath: str, quiz: Quiz, settings: dict) -> None:
    """Guarda el estado del quiz para poder reanudarlo despues.

    settings es el dict de configuracion (Settings.as_dict). El backup del
    orden exacto de preguntas se incluye en el JSON, asi el resume no depende
    de re-cargar el archivo CSV de nuevo.
    """
    data = {
        "version": PROGRESS_VERSION,
        "settings": dict(settings),
        "questions": [
            {
                "pregunta": q.texto,
                "opciones": list(q.opciones),
                "respuesta_correcta": q.respuesta_correcta,
                "nivel": q.nivel,
            }
            for q in quiz.questions
        ],
        "current_index": quiz.current_index,
        "score": quiz.score,
        "stats": quiz.stats,
        "time_remaining": quiz.time_remaining,
        "question_time": round(quiz.question_time, 3),
        "total_time_used": round(quiz.total_time_used, 3),
        "times_responded": [round(t, 3) for t in quiz.times_responded],
        "answer_result": quiz.answer_result,
        "current_streak": quiz.current_streak,
        "max_streak": quiz.max_streak,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_progress(filepath: str) -> Optional[dict]:
    """Carga el JSON de progreso. Devuelve None si no existe o esta corrupto."""
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def clear_progress(filepath: str) -> None:
    """Borra el archivo de progreso si existe."""
    if os.path.exists(filepath):
        os.remove(filepath)


def resume_quiz(data: dict) -> Quiz:
    """Reconstruye un Quiz a partir del dict guardado por save_progress()."""
    settings = dict(data.get("settings") or {})
    questions = [
        Question.from_dict(q) for q in (data.get("questions") or []) if isinstance(q, dict)
    ]
    if not questions:
        raise ValueError("Progreso sin preguntas validas")

    settings["num_questions"] = len(questions)
    quiz = Quiz(questions, settings)
    # Respetar el orden guardado (Quiz.__init__ barajaria de nuevo)
    quiz.questions = questions
    quiz.num_questions = len(questions)

    quiz.current_index = max(0, min(int(data.get("current_index", 0)),
                                    len(questions) - 1))
    quiz.score = int(data.get("score", 0))

    stats = data.get("stats") or {}
    for lvl in VALID_LEVELS:
        st = stats.get(lvl) or {}
        quiz.stats[lvl]["correctas"] = int(st.get("correctas", 0))
        quiz.stats[lvl]["incorrectas"] = int(st.get("incorrectas", 0))

    tr = data.get("time_remaining")
    quiz.time_remaining = tr if isinstance(tr, (int, float)) else \
        settings.get("time_per_question")

    quiz.question_time = float(data.get("question_time", 0.0))
    quiz.total_time_used = float(data.get("total_time_used", 0.0))
    quiz.times_responded = [float(t) for t in (data.get("times_responded") or [])]

    ar = data.get("answer_result")
    quiz.answer_result = ar if isinstance(ar, dict) else None

    quiz.current_streak = int(data.get("current_streak", 0))
    quiz.max_streak = int(data.get("max_streak", 0))
    return quiz
