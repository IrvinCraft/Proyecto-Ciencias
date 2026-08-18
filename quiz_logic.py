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
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger("quiz.logic")


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
VALID_LEVELS = ("facil", "media", "dificil", "ultra_dificil")


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
    def _load_csv(filepath: str) -> List[Question]:
        """Carga preguntas desde CSV.
        Columnas: pregunta, opcion_a..d, respuesta_correcta, nivel
        respuesta_correcta indica la letra (A, B, C o D) de la opcion valida.
        """
        questions: List[Question] = []
        opcion_cols = ["opcion_a", "opcion_b", "opcion_c", "opcion_d"]
        with open(filepath, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            required_cols = {"pregunta", "respuesta_correcta", "nivel"}
            col_names = set(reader.fieldnames or [])
            missing = required_cols - col_names
            if missing:
                raise ValueError(f"Columnas faltantes en CSV: {missing}")

            if set(opcion_cols) - col_names:
                raise ValueError(
                    f"CSV necesita 4 columnas de opciones: {', '.join(opcion_cols)}"
                )

            for i, row in enumerate(reader):
                data = {
                    "pregunta": row["pregunta"],
                    "opciones": [row[c] for c in opcion_cols],
                    "respuesta_correcta": row["respuesta_correcta"],
                    "nivel": row["nivel"],
                }
                try:
                    letra = str(data["respuesta_correcta"]).strip().upper()
                    if letra not in "ABCD":
                        raise ValueError(
                            f"respuesta_correcta debe ser A, B, C o D (se obtuvo "
                            f"'{row['respuesta_correcta']}')"
                        )
                    data["respuesta_correcta"] = data["opciones"]["ABCD".index(letra)]
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
        """Lee un CSV contando las filas validas e ignorando las malformadas."""
        questions: List[Question] = []
        skipped = 0
        opcion_cols = ["opcion_a", "opcion_b", "opcion_c", "opcion_d"]
        with open(filepath, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            col_names = set(reader.fieldnames or [])
            missing = {"pregunta", "respuesta_correcta", "nivel"} - col_names
            if missing:
                raise ValueError(f"Columnas faltantes en CSV: {missing}")
            if set(opcion_cols) - col_names:
                raise ValueError(
                    f"CSV necesita 4 columnas de opciones: {', '.join(opcion_cols)}"
                )

            for row in reader:
                try:
                    if not (str(row.get("pregunta") or "").strip()):
                        raise ValueError("pregunta vacia")
                    letra = str(row.get("respuesta_correcta") or "").strip().upper()
                    if letra not in "ABCD":
                        raise ValueError(
                            f"respuesta_correcta debe ser A, B, C o D "
                            f"(se obtuvo '{row.get('respuesta_correcta')}')"
                        )
                    opciones = [row[c] for c in opcion_cols]
                    data = {
                        "pregunta": row["pregunta"],
                        "opciones": opciones,
                        "respuesta_correcta": opciones["ABCD".index(letra)],
                        "nivel": row["nivel"],
                    }
                    questions.append(Question.from_dict(data))
                except (ValueError, KeyError, IndexError):
                    skipped += 1

            if not questions:
                raise ValueError(
                    f"No hay filas validas en el CSV (se ignoraron {skipped} filas)"
                )
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
            "stats": dict(self.stats),
        }
