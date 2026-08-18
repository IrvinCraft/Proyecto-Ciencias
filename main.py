#!/usr/bin/env python3
"""
main.py
=======
Punto de entrada de la aplicacion del Quiz Educativo.
Interfaz grafica con Pygame (animaciones, sonidos, botones clicables).

Uso:  python main.py
"""
import os
import sys
import math
import random
import shutil
import subprocess
import threading
import traceback
import logging
import pygame

# Asegurar el path del directorio del script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from quiz_logic import QuestionLoader, Quiz, VALID_LEVELS
from settings import Settings
from question_bank import import_csv_to_bank, list_sessions
from paths import data_dir, resource_dir
import updater as updater_mod
from updater import VERSION as APP_VERSION

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FILE = os.path.join(data_dir(), "quiz.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("quiz")


def _log_uncaught(exc_type, exc_value, exc_tb):
    """Registra cualquier excepcion que escape del bucle principal."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger.critical(
        "Excepcion no capturada:\n%s",
        "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
    )


sys.excepthook = _log_uncaught

# ---------------------------------------------------------------------------
# Constantes de pantalla
# ---------------------------------------------------------------------------
DEFAULT_WIDTH, DEFAULT_HEIGHT = 1280, 720
MIN_WIDTH, MIN_HEIGHT = 800, 600
FPS = 60

# Paleta de colores
BG_DARK = (15, 20, 40)
BG_GRADIENT_TOP = (15, 20, 40)
BG_GRADIENT_BOT = (30, 35, 55)
PANEL = (30, 40, 70)
BUTTON = (70, 85, 130)
BUTTON_HOVER = (95, 115, 170)
BUTTON_ACTIVE = (60, 75, 120)
TEXT_LIGHT = (245, 245, 245)
TEXT_MUTED = (180, 185, 210)
ACCENT = (255, 215, 0)
CORRECT_GREEN = (46, 204, 113)
INCORRECT_RED = (231, 76, 60)
PROGRESS_BG = (50, 60, 90)
PROGRESS_FILL = (100, 180, 255)
WARNING_ORANGE = (255, 165, 0)

# Niveles de dificultad y sus etiquetas
LEVEL_LABELS = {
    "facil": "Facil",
    "media": "Media",
    "dificil": "Dificil",
    "ultra_dificil": "Ultra Dificil",
}
LEVEL_COLORS = {
    "facil": (86, 209, 153),
    "media": (241, 196, 15),
    "dificil": (236, 112, 96),
    "ultra_dificil": (155, 89, 182),
}

BASE_FONT_SIZES = {
    "title": 48, "large": 36, "medium": 24,
    "small": 18, "question": 28, "option": 22,
}
BOLD_FONTS = {"title", "large", "question"}

# ---------------------------------------------------------------------------
# Screen states
# ---------------------------------------------------------------------------
SCREEN_START = "start"
SCREEN_SETTINGS = "settings"
SCREEN_QUIZ = "quiz"
SCREEN_RESULTS = "results"
SCREEN_ERROR = "error"
SCREEN_IMPORT = "import"
SCREEN_UPDATE = "update"


# ---------------------------------------------------------------------------
# SoundManager
# ---------------------------------------------------------------------------
class SoundManager:
    """Carga y administra todos los efectos de sonido del juego."""

    def __init__(self, sounds_dir):
        self.sounds = {}
        self.sounds_dir = sounds_dir
        self._load_all()
        self.enabled = True

    def _load_all(self):
        """Carga los archivos .wav desde assets/sounds/."""
        expected = ["click", "start", "error", "correct", "celebration"]
        for name in expected:
            path = os.path.join(self.sounds_dir, name + ".wav")
            if os.path.exists(path):
                try:
                    self.sounds[name] = pygame.mixer.Sound(path)
                except pygame.error:
                    print(f"  [WARN] No se pudo cargar: {name}.wav")
            else:
                print(f"  [WARN] Archivo no encontrado: {name}.wav")

    def play(self, name):
        """ Reproduce un efecto de sonido por nombre."""
        if self.enabled and name in self.sounds:
            self.sounds[name].play()

    def play_music_start(self):
        """Sonido de inicio de la aplicacion."""
        self.play("start")


# ---------------------------------------------------------------------------
# UI: Button
# ---------------------------------------------------------------------------
class Button:
    """Boton clicable con efecto hover."""

    def __init__(self, rect, text, font, bg=BUTTON, hover=BUTTON_HOVER,
                 text_color=TEXT_LIGHT):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.bg = bg
        self.hover = hover
        self.text_color = text_color
        self.hovered = False
        self.enabled = True
        self._render()

    def _render(self):
        self.text_surf = self.font.render(self.text, True, self.text_color)
        # Autoajuste: si el texto es mas ancho/alto que el boton, se escala
        # para que no sobresalga (evita letras montadas fuera del rectangulo).
        max_w = max(self.rect.width - 16, 12)
        max_h = max(self.rect.height - 10, 8)
        w, h = self.text_surf.get_size()
        if w > max_w or h > max_h:
            scale = min(max_w / w, max_h / h)
            nw = max(int(w * scale), 1)
            nh = max(int(h * scale), 1)
            self.text_surf = pygame.transform.smoothscale(self.text_surf, (nw, nh))
        self.text_rect = self.text_surf.get_rect(center=self.rect.center)

    def draw(self, surface):
        color = self.hover if (self.hovered and self.enabled) else self.bg
        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        pygame.draw.rect(surface, ACCENT, self.rect, 2, border_radius=8)
        surface.blit(self.text_surf, self.text_rect)

    def handle_event(self, event):
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos) and self.enabled:
                return True
        return False


# ---------------------------------------------------------------------------
# UI: InputBox
# ---------------------------------------------------------------------------
class InputBox:
    """Campo de texto editable, con validacion numerica opcional."""

    def __init__(self, rect, font, default_text="", numeric=False):
        self.rect = pygame.Rect(rect)
        self.font = font
        self.text = default_text
        self.numeric = numeric
        self.active = False
        self.placeholder = "Ingrese valor"
        self._render()

    def _render(self):
        if self.text:
            self.surf = self.font.render(self.text, True, TEXT_LIGHT)
        else:
            self.surf = self.font.render(self.placeholder, True, TEXT_MUTED)
        self.text_rect = self.surf.get_rect()
        # Centrar verticalmente
        self.text_rect.centery = self.rect.centery

    def draw(self, surface):
        border_color = ACCENT if self.active else BUTTON_HOVER
        bg_color = PANEL if not self.active else (45, 55, 90)
        pygame.draw.rect(surface, bg_color, self.rect, border_radius=5)
        pygame.draw.rect(surface, border_color, self.rect, 2, border_radius=5)
        surface.blit(self.surf, (self.rect.x + 8, self.text_rect.centery - self.surf.get_height() // 2))

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            was_active = self.active
            self.active = self.rect.collidepoint(event.pos)
            if self.active != was_active:
                self._render()
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_RETURN:
                self.active = False
                self._render()
                return True  # confirma
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_TAB:
                pass
            else:
                char = event.unicode
                if self.numeric:
                    if char.isdigit():
                        self.text += char
                    elif char == "." and "." not in self.text:
                        self.text += char
                else:
                    if len(char) == 1 and char.isprintable():
                        self.text += char
            self._render()
        return False

    @property
    def value(self):
        """Devuelve el valor procesado (int/float/str)."""
        if self.text:
            if self.numeric:
                try:
                    if "." in self.text:
                        return float(self.text)
                    return int(self.text)
                except ValueError:
                    return None
            return self.text
        return None

    @value.setter
    def value(self, val):
        self.text = str(val)
        self._render()


# ---------------------------------------------------------------------------
# UI: Checkbox
# ---------------------------------------------------------------------------
class Checkbox:
    """Checkbox simple para activar/desactivar opciones."""

    def __init__(self, rect, font, label="", label_color=TEXT_LIGHT):
        self.rect = pygame.Rect(rect)
        self.check_rect = pygame.Rect(
            self.rect.x, self.rect.y, self.rect.height, self.rect.height
        )
        self.font = font
        self.label = label
        self.label_color = label_color
        self.checked = False
        self.hovered = False

    def draw(self, surface):
        color = ACCENT if self.checked else PANEL
        pygame.draw.rect(surface, color, self.check_rect, border_radius=3)
        pygame.draw.rect(surface, BUTTON_HOVER, self.check_rect, 2, border_radius=3)
        if self.checked:
            # Dibujar checkmark
            x, y = self.check_rect.center
            size = self.check_rect.width // 5
            pygame.draw.line(surface, TEXT_LIGHT,
                             (x - size, y - size), (x, y + size), 2)
            pygame.draw.line(surface, TEXT_LIGHT,
                             (x, y + size), (x + size + 2, y - size - 4), 2)
        label_surf = self.font.render(self.label, True, self.label_color)
        surface.blit(label_surf, (self.check_rect.right + 10, self.rect.y + (self.check_rect.height - label_surf.get_height()) // 2))

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.check_rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.check_rect.collidepoint(event.pos):
                self.checked = not self.checked
                return True
        return False


# ---------------------------------------------------------------------------
# SpaceBackground (fondo tematico de ciencias/espacio)
# ---------------------------------------------------------------------------
class SpaceBackground:
    """Fondo espacial: gradiente + estrellas fijas y parpadeantes, planetas
    que giran y un cometa ocasional. Las superficies pesadas se pre-renderizan
    en reset() para no recalcularlas cada frame."""

    def __init__(self):
        self.base = None
        self.size = (0, 0)
        self.twinkle = []
        self.rng = random.Random(7)
        self.time = 0.0
        self.planet = None
        self.planet_size = 170
        self.small_planet = None
        self.comet = None
        self.next_comet = 3.0

    # -- construccion (una vez por tamano de ventana) -----------------------
    def reset(self, w, h):
        self.size = (w, h)
        self._build_base(w, h)
        self._build_twinkle(w, h)
        self._build_planets()

    def _build_base(self, w, h):
        base = pygame.Surface((w, h), pygame.SRCALPHA)
        top, bot = BG_GRADIENT_TOP, BG_GRADIENT_BOT
        for y in range(h):
            t = y / h
            r = int(top[0] + (bot[0] - top[0]) * t)
            g = int(top[1] + (bot[1] - top[1]) * t)
            b = int(top[2] + (bot[2] - top[2]) * t)
            pygame.draw.line(base, (r, g, b, 255), (0, y), (w, y))
        # Estrellas fijas (tenues, forman parte del fondo de todas las pantallas)
        for _ in range(int(w * h / 4200)):
            x = self.rng.randrange(w)
            y = self.rng.randrange(h)
            s = self.rng.choice([1, 1, 2])
            a = self.rng.randint(40, 130)
            c = self.rng.choice([(255, 255, 255), (255, 230, 160), (190, 210, 255)])
            pygame.draw.rect(base, (*c, a), (x, y, s, s))
        self.base = base

    def _build_twinkle(self, w, h):
        self.twinkle = []
        for _ in range(int(w * h / 9000)):
            self.twinkle.append({
                "x": self.rng.randrange(w),
                "y": self.rng.randrange(h),
                "r": self.rng.choice([1, 1, 2]),
                "phase": self.rng.uniform(0, 6.28),
                "speed": self.rng.uniform(0.8, 2.5),
                "min": self.rng.randint(50, 120),
                "max": self.rng.randint(200, 255),
                "base": self.rng.choice([(255, 255, 255), (255, 240, 170), (180, 210, 255)]),
            })

    def _build_planets(self):
        if self.planet is None:
            self.planet = self._render_planet(self.planet_size, seed=3)
        if self.small_planet is None:
            self.small_planet = self._render_planet(70, seed=11)
        self.comet = None
        self.next_comet = self.rng.uniform(3, 7)

    def _render_comet(self):
        c = pygame.Surface((50, 14), pygame.SRCALPHA)
        for i in range(42):
            a = int(170 * (1 - i / 42))
            pygame.draw.rect(c, (255, 255, 255, a), (i, 5, 2, 2))
        pygame.draw.circle(c, (255, 255, 255, 255), (48, 7), 3)
        pygame.draw.circle(c, (255, 240, 200, 210), (48, 7), 2)
        return c

    @staticmethod
    def _render_planet(size, seed):
        rng = random.Random(seed)
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy = size // 2
        radius = size // 2 - 3
        base_col = rng.choice([(50, 90, 200), (170, 90, 60), (70, 120, 190)])
        light = tuple(min(255, int(c * 1.8)) for c in base_col)
        # Esfera (gradiente radial: borde oscuro, centro claro)
        for r in range(radius, 0, -1):
            k = 1 - (r / radius)
            col = (
                int(base_col[0] + (light[0] - base_col[0]) * k),
                int(base_col[1] + (light[1] - base_col[1]) * k),
                int(base_col[2] + (light[2] - base_col[2]) * k),
            )
            pygame.draw.circle(surf, (*col, 255), (cx, cy), r)
        # "Continentes"
        land = rng.choice([(60, 140, 70), (140, 110, 60), (50, 130, 110)])
        for _ in range(rng.randint(5, 9)):
            w_ = rng.randint(radius // 4, radius // 2)
            h_ = rng.randint(radius // 5, radius // 2)
            e = pygame.Rect(
                cx - w_ // 2 + rng.randint(-radius // 3, radius // 3),
                cy - h_ // 2 + rng.randint(-radius // 3, radius // 3),
                w_, h_,
            )
            pygame.draw.ellipse(surf, (*land, 255), e)
        # Mascara circular: recorta lo que este fuera de la esfera
        mask = pygame.Surface((size, size), pygame.SRCALPHA)
        mask.fill((0, 0, 0, 0))
        pygame.draw.circle(mask, (255, 255, 255, 255), (cx, cy), radius)
        surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        # Brillo especular arriba-izquierda
        pygame.draw.circle(surf, (255, 255, 255, 60),
                           (cx - radius // 3, cy - radius // 3), radius // 4)
        return surf

    # -- dibujo animado ------------------------------------------------------
    def draw(self, surface, t):
        """Dibuja el fondo animado (inicio). t = segundos transcurridos."""
        dt = t - self.time
        self.time = t
        w, h = surface.get_size()
        if self.size != (w, h):
            self.reset(w, h)

        surface.blit(self.base, (0, 0))

        # Estrellas parpadeantes (brillo variable, sin superficies por frame)
        for s in self.twinkle:
            k = (math.sin(t * s["speed"] + s["phase"]) + 1) / 2
            b = int(s["min"] + (s["max"] - s["min"]) * k)
            col = tuple(min(255, int(c * b / 255)) for c in s["base"])
            pygame.draw.rect(surface, col, (s["x"], s["y"], s["r"], s["r"]))

        # Planeta principal (abajo-izquierda)
        rot = pygame.transform.rotate(self.planet, (t * 12) % 360)
        surface.blit(
            rot,
            (40 - rot.get_width() // 2, h - 30 - rot.get_height() // 2)
        )

        # Planeta pequeno (arriba-derecha)
        rot2 = pygame.transform.rotate(self.small_planet, (t * -10) % 360)
        surface.blit(
            rot2,
            (w - 80 - rot2.get_width() // 2, 40 - rot2.get_height() // 2)
        )

        # Cometa ocasional
        if self.comet is None:
            self.next_comet -= dt
            if self.next_comet <= 0:
                ang = self.rng.uniform(math.radians(35), math.radians(60))
                speed = self.rng.uniform(h * 0.25, h * 0.40)
                self.comet = {
                    "x": self.rng.uniform(-80, w * 0.5),
                    "y": self.rng.uniform(-40, h * 0.3),
                    "vx": math.cos(ang) * speed,
                    "vy": math.sin(ang) * speed,
                    "surf": self._render_comet(),
                }
        else:
            c = self.comet
            c["x"] += c["vx"] * dt
            c["y"] += c["vy"] * dt
            surface.blit(c["surf"], (int(c["x"]), int(c["y"])))
            if c["x"] > w + 80 or c["y"] > h + 80:
                self.comet = None
                self.next_comet = self.rng.uniform(5, 12)


# ---------------------------------------------------------------------------
# Game (main)
# ---------------------------------------------------------------------------
class Game:
    """Clase principal: gestiona pantallas, eventos, animaciones y sonido."""

    def __init__(self):
        logger.info("Iniciando Game...")
        os.environ["SDL_VIDEO_CENTERED"] = "1"
        pygame.init()
        pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)

        self.width, self.height = DEFAULT_WIDTH, DEFAULT_HEIGHT
        self.screen = pygame.display.set_mode(
            (self.width, self.height), pygame.RESIZABLE
        )
        pygame.display.set_caption("Quiz Educativo")
        self.clock = pygame.time.Clock()
        logger.info("Ventana %dx%d (RESIZABLE) creada", self.width, self.height)

        # Sonidos
        sounds_dir = os.path.join(resource_dir(), "assets", "sounds")
        self.sounds = SoundManager(sounds_dir)
        logger.info("Cargados %d sonidos", len(self.sounds.sounds))

        # Configuracion
        self.settings = Settings()
        logger.info("Config: num_questions=%s levels=%s time=%s unlimited=%s archivo=%s",
                    self.settings.num_questions, self.settings.levels,
                    self.settings.time_per_question, self.settings.unlimited_time,
                    self.settings.question_file)

        # Estado del juego
        self.quiz: Quiz = None
        self.screen_state = SCREEN_START
        self.error_message = ""
        self.settings_warning = ""
        self.import_message = ""
        self.import_message_color = TEXT_LIGHT
        self.import_message_until = 0

        # Animaciones
        self.fade_alpha = 0        # 0 = visible, 255 = negro total
        self.fade_direction = 0    # +1 = fade out (a negro), -1 = fade in, 0 = idle
        self.fade_speed = 300      # pixeles de alpha por segundo
        self.pending_next = False  # True = hay que avanzar de pregunta en el negro
        self.flash_color = None    # (r,g,b) o None
        self.flash_timer = 0.0
        self.flash_duration = 0.5
        self.show_next_button = False

        # Fuentes y UI
        self.space = SpaceBackground()
        self.space.reset(self.width, self.height)
        self._load_scaled_fonts()
        self._build_start_screen()
        self._build_start_overlay()
        self._build_settings_screen()
        self._build_error_screen()
        self._build_results_screen()
        self.import_sessions = []
        self.import_scroll = 0
        self._build_import_screen()
        self._build_update_screen()
        logger.info("UI inicializada")

        self.update_info = {"state": "checking", "info": None, "error": "", "applied": ""}
        self._start_update_check()

        self.running = True

    # -- fuentes / escala ----------------------------------------------------
    def _load_font(self, size, bold=False):
        """Carga una fuente del sistema con fallback al default de Pygame."""
        for name in ["dejavusans", "arial", "verdana"]:
            try:
                return pygame.font.SysFont(name, size, bold=bold)
            except:
                continue
        return pygame.font.Font(None, size)

    def _scale_factor(self) -> float:
        """Factor de escala proporcional al tamano de la ventana."""
        return max(0.55, min(2.5, min(
            self.width / DEFAULT_WIDTH, self.height / DEFAULT_HEIGHT
        )))

    def _load_scaled_fonts(self):
        """Recarga las fuentes escaladas al tamano actual de la ventana."""
        scale = self._scale_factor()
        for key, size in BASE_FONT_SIZES.items():
            bold = key in BOLD_FONTS
            setattr(self, f"font_{key}", self._load_font(int(size * scale), bold=bold))

    def _rebuild_all_ui(self):
        """Reconstruye toda la interfaz segun el tamano actual de la ventana."""
        snapshot = None
        if self.screen_state == SCREEN_SETTINGS and hasattr(self, "settings_inputs"):
            snapshot = self._snapshot_settings_ui()
        self._load_scaled_fonts()
        self._build_start_screen()
        self._build_start_overlay()
        self._build_settings_screen()
        self._build_error_screen()
        self._build_results_screen()
        self._build_import_screen()
        self._build_update_screen()
        if self.quiz:
            self._build_quiz_ui()
        if snapshot is not None:
            self._restore_settings_ui(snapshot)

    # -- builders de pantallas ------------------------------------------------
    def _build_start_screen(self):
        """Crea los elementos de la pantalla de inicio (3 botones apilados)."""
        w, h = self.width, self.height
        btn_w, btn_h = 240, int(max(46, min(60, h * 0.075)))
        gap = int(max(22, min(34, h * 0.042)))
        cx = w // 2
        btn_top = int(h * 0.30) + 130  # debajo del titulo/subtitulo
        btn_x = cx - btn_w // 2
        self.btn_start = Button(
            (btn_x, btn_top, btn_w, btn_h),
            "Comenzar Quiz", self.font_large
        )
        self.btn_settings = Button(
            (btn_x, btn_top + (btn_h + gap), btn_w, btn_h),
            "Ajustes", self.font_medium
        )
        self.btn_quit = Button(
            (btn_x, btn_top + 2 * (btn_h + gap), btn_w, btn_h),
            "Salir", self.font_medium
        )
        self.btn_update = Button(
            (btn_x, btn_top + 3 * (btn_h + gap), btn_w, btn_h),
            "Actualizaciones", self.font_medium
        )

    def _build_start_overlay(self):
        """Capa semitransparente vertical para legibilidad sobre el fondo animado."""
        w, h = self.width, self.height
        ov = pygame.Surface((w, h), pygame.SRCALPHA)
        center = h * 0.50
        half = h * 0.42
        y0 = max(0, int(center - half))
        y1 = min(h, int(center + half))
        for y in range(y0, y1):
            k = 1 - abs((y - center) / half)
            a = int(135 * k)
            pygame.draw.line(ov, (5, 8, 18, a), (0, y), (w, y))
        self.start_overlay = ov

    def _add_settings_label(self, text, font, x0, y, max_w, color=TEXT_LIGHT):
        """Agrega una etiqueta de ajustes envolviendola en varias lineas si no cabe.
        Devuelve la altura (en px) que ocupa el bloque de lineas."""
        if font.render(text, True, color).get_width() <= max_w:
            lines = [text]
        else:
            lines, cur = [], ""
            for word in text.split(" "):
                test = (cur + " " + word).strip()
                if font.render(test, True, color).get_width() > max_w and cur:
                    lines.append(cur)
                    cur = word
                else:
                    cur = test
            if cur:
                lines.append(cur)
        line_h = font.get_height() + 4
        for i, ln in enumerate(lines):
            self.settings_labels.append((font.render(ln, True, color), x0, y + i * line_h))
        return len(lines) * line_h

    def _build_settings_screen(self):
        """Crea los elementos interactivos de la pantalla de ajustes."""
        self.settings_inputs = {}
        self.level_checks = {}
        self.settings_labels = []

        w, h = self.width, self.height
        panel = pygame.Rect(int(w * 0.05), 64, int(w * 0.90), int(h * 0.82))
        x0 = panel.x + 30
        xl = x0 + 300
        label_max_w = xl - x0 - 16  # ancho maximo de las etiquetas (no tocan el input)

        iw, ih = 110, 32  # tamanos de input

        cursor = panel.y + 44

        # --- Fila A: numero de preguntas ---
        h_a = self._add_settings_label(
            "Número de preguntas (4-100):", self.font_medium,
            x0, cursor + 4, label_max_w
        )
        self.settings_inputs["num_questions"] = InputBox(
            (xl, cursor, iw, ih), self.font_medium,
            str(self.settings.num_questions), numeric=True
        )
        cursor += max(h_a, ih) + 20

        # --- Fila B: nivel de dificultad (2 lineas de checkboxes) ---
        h_b = self._add_settings_label(
            "Nivel de dificultad:", self.font_medium,
            x0, cursor + 6, label_max_w
        )
        chk_w, chk_h = 16, 22
        l1 = cursor + 2
        l2 = cursor + 32
        level_spacing = 150
        for i, lvl in enumerate(VALID_LEVELS[:3]):
            self.level_checks[lvl] = Checkbox(
                (xl + i * level_spacing, l1, chk_w, chk_h),
                self.font_small, LEVEL_LABELS[lvl], LEVEL_COLORS[lvl]
            )
        self.level_checks["ultra_dificil"] = Checkbox(
            (xl, l2, chk_w, chk_h), self.font_small,
            LEVEL_LABELS["ultra_dificil"], LEVEL_COLORS["ultra_dificil"]
        )
        self.chk_all = Checkbox(
            (xl + level_spacing, l2, chk_w, chk_h), self.font_small,
            "Todos los niveles", TEXT_LIGHT
        )
        cursor += max(h_b, l2 + chk_h - cursor - 2) + 20

        # --- Fila C: puntos por nivel (4 inputs en una fila) ---
        h_c = self._add_settings_label(
            "Puntos por nivel:", self.font_medium,
            x0, cursor + 6, label_max_w
        )
        points_area = panel.width - (xl - panel.x) - 20
        slot = points_area // 4
        inp_w = min(70, slot - 20)
        for i, lvl in enumerate(VALID_LEVELS):
            xc = xl + i * slot + (slot - inp_w) // 2
            self.settings_labels.append((
                self.font_small.render(LEVEL_LABELS[lvl], True, LEVEL_COLORS[lvl]),
                xc, cursor + 22
            ))
            self.settings_inputs[f"points_{lvl}"] = InputBox(
                (xc, cursor + 40, inp_w, ih), self.font_small,
                str(self.settings.points[lvl]), numeric=True
            )
        cursor += max(h_c, 40 + ih) + 20

        # --- Fila D: tiempo por pregunta ---
        h_d = self._add_settings_label(
            "Tiempo por pregunta (segundos):", self.font_medium,
            x0, cursor + 4, label_max_w
        )
        self.settings_inputs["time_per_question"] = InputBox(
            (xl, cursor, iw, ih), self.font_medium,
            str(self.settings.time_per_question), numeric=True
        )
        self.chk_unlimited = Checkbox(
            (xl + iw + 30, cursor + 4, chk_w, chk_h), self.font_small,
            "Tiempo ilimitado", TEXT_LIGHT
        )
        cursor += max(h_d, ih) + 20

        # --- Botones ---
        btn_w, btn_h = 220, 42
        by = panel.bottom - 100
        self.btn_back_settings = Button(
            (24, 18, 120, 42),
            "Volver", self.font_medium
        )
        self.btn_save = Button(
            (panel.x + 30, by, btn_w, btn_h),
            "Guardar Configuración", self.font_small
        )
        self.btn_restore = Button(
            (panel.x + 30 + btn_w + 20, by, btn_w, btn_h),
            "Restaurar Valores", self.font_small
        )
        self.btn_start_quiz = Button(
            (panel.centerx - 120, panel.bottom - 50, 240, 46),
            "Comenzar Quiz", self.font_large
        )

        self._refresh_settings_inputs()

    def _refresh_settings_inputs(self):
        """Sincroniza los InputBox y checkboxes con los valores de Settings."""
        self.settings_inputs["num_questions"].value = self.settings.num_questions
        for lvl in VALID_LEVELS:
            self.settings_inputs[f"points_{lvl}"].value = self.settings.points[lvl]
        self.settings_inputs["time_per_question"].value = self.settings.time_per_question
        self.chk_unlimited.checked = self.settings.unlimited_time
        selected = set(self.settings.levels)
        for lvl in VALID_LEVELS:
            self.level_checks[lvl].checked = lvl in selected
        self.chk_all.checked = all(c.checked for c in self.level_checks.values())

    def _snapshot_settings_ui(self) -> dict:
        """Captura el texto/estado actual de los controles (para reconstruir)."""
        snap = {
            "inputs": {k: inp.text for k, inp in self.settings_inputs.items()},
            "unlimited": self.chk_unlimited.checked,
            "levels": {lvl: c.checked for lvl, c in self.level_checks.items()},
            "all": self.chk_all.checked,
            "warning": self.settings_warning,
        }
        return snap

    def _restore_settings_ui(self, snap: dict):
        for k, text in snap["inputs"].items():
            if k in self.settings_inputs:
                self.settings_inputs[k].text = text
                self.settings_inputs[k]._render()
        self.chk_unlimited.checked = snap["unlimited"]
        for lvl, checked in snap["levels"].items():
            self.level_checks[lvl].checked = checked
        self.chk_all.checked = snap["all"]
        self.settings_warning = snap.get("warning", "")

    def _build_quiz_ui(self):
        """Crea los botones de opciones para la pantalla de quiz."""
        self.option_buttons = []
        w, h = self.width, self.height
        btn_w = int(min(720, w * 0.56))
        btn_h = int(h * 0.08)
        start_x = (w - btn_w) // 2
        start_y = int(h * 0.48)
        spacing = int(h * 0.095)
        for i in range(4):
            btn = Button(
                (start_x, start_y + i * spacing, btn_w, btn_h),
                "", self.font_option,
                bg=PANEL, hover=(55, 70, 110)
            )
            btn.index = i
            self.option_buttons.append(btn)

        self.btn_next = Button(
            (w // 2 - 80, h - 80, 160, 45),
            "Siguiente", self.font_medium
        )
        self.btn_next.enabled = True

    def _build_error_screen(self):
        """Crea botones para la pantalla de error."""
        self.btn_back_to_settings = Button(
            (self.width // 2 - 100, self.height - 100, 200, 45),
            "Volver a Ajustes", self.font_medium
        )

    def _build_results_screen(self):
        """Crea botones para la pantalla de resultados."""
        btn_w = 220
        self.btn_retry = Button(
            (self.width // 2 - btn_w - 20, self.height - 100, btn_w, 50),
            "Reintentar", self.font_large
        )
        self.btn_back_settings_r = Button(
            (self.width // 2 + 20, self.height - 100, btn_w, 50),
            "Volver a Ajustes", self.font_large
        )

    # -- draw helpers ---------------------------------------------------------
    def _draw_gradient_bg(self, surface):
        """Fondo pre-renderizado (degradado + estrellas fijas). Un solo blit."""
        if self.space.size != (self.width, self.height):
            self.space.reset(self.width, self.height)
        surface.blit(self.space.base, (0, 0))

    def _draw_top_bar(self):
        """Dibuja la barra superior: puntaje, cronometro, progreso."""
        bar_h = int(self.height * 0.09)
        bar_surf = pygame.Surface((self.width, bar_h), pygame.SRCALPHA)
        bar_surf.fill((20, 30, 55, 200))
        self.screen.blit(bar_surf, (0, 0))
        mid_y = bar_h // 2 - 10

        # Puntaje
        score_surf = self.font_medium.render(
            f"Puntaje: {self.quiz.score}", True, ACCENT
        )
        self.screen.blit(score_surf, (20, mid_y))

        # Cronometro (congelado si ya respondio)
        if self.quiz.answer_result is not None:
            t = self.quiz.answer_result["tiempo_usado"]
            timer_text = f"Respondiste en: {t:.2f}s"
            color = TEXT_LIGHT
        elif self.quiz.unlimited_time:
            timer_text = f"Tiempo: {self.quiz.question_time:.1f}s"
            color = TEXT_LIGHT
        else:
            remaining = self.quiz.time_remaining
            if remaining <= 3:
                color = INCORRECT_RED
            elif remaining <= 7:
                color = WARNING_ORANGE
            else:
                color = TEXT_LIGHT
            timer_text = f"Tiempo: {remaining:.1f}s"
        timer_surf = self.font_medium.render(timer_text, True, color)
        self.screen.blit(
            timer_surf, (self.width // 2 - timer_surf.get_width() // 2, mid_y)
        )

        # Progreso
        prog_text = f"Pregunta {self.quiz.question_number} de {self.quiz.num_questions}"
        prog_surf = self.font_medium.render(prog_text, True, TEXT_LIGHT)
        self.screen.blit(
            prog_surf, (self.width - prog_surf.get_width() - 20, mid_y)
        )

        # Barra de progreso
        bar_width = int(self.width * 0.30)
        bar_height = max(6, int(self.height * 0.012))
        bx = (self.width - bar_width) // 2
        by = bar_h - bar_height - 10
        pygame.draw.rect(self.screen, PROGRESS_BG,
                         (bx, by, bar_width, bar_height), border_radius=4)
        progress = self.quiz.question_number / self.quiz.num_questions
        fill_width = int(bar_width * progress)
        if fill_width > 0:
            pygame.draw.rect(self.screen, PROGRESS_FILL,
                             (bx, by, fill_width, bar_height), border_radius=4)

    def _draw_flash_effect(self):
        """Dibuja el overlay de color al responder."""
        if self.flash_color and self.flash_timer > 0:
            overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            alpha = int(180 * (self.flash_timer / self.flash_duration))
            overlay.fill((*self.flash_color, alpha))
            self.screen.blit(overlay, (0, 0))

    def _draw_fade(self):
        """Dibuja el overlay de fundido negro para transiciones."""
        if self.fade_alpha > 0:
            overlay = pygame.Surface((self.width, self.height))
            overlay.set_alpha(self.fade_alpha)
            overlay.fill((0, 0, 0))
            self.screen.blit(overlay, (0, 0))

    # -- pantalla de inicio --------------------------------------------------
    def draw_start_screen(self):
        t = pygame.time.get_ticks() / 1000
        self.space.draw(self.screen, t)
        self.screen.blit(self.start_overlay, (0, 0))

        # Logo/titulo con animacion de pulsado
        scale = 1.0 + 0.02 * math.sin(t * 2)
        title1 = self.font_title.render("QUIZ", True, ACCENT)
        title2 = self.font_title.render("EDUCATIVO", True, TEXT_LIGHT)
        ty = int(self.height * 0.30)
        self.screen.blit(
            pygame.transform.scale(title1,
                (int(title1.get_width() * scale), int(title1.get_height() * scale))),
            (self.width // 2 - title1.get_width() * scale // 2, ty - 40)
        )
        self.screen.blit(
            pygame.transform.scale(title2,
                (int(title2.get_width() * scale), int(title2.get_height() * scale))),
            (self.width // 2 - title2.get_width() * scale // 2, ty + 10)
        )

        subtitle = self.font_medium.render(
            "Preguntas de conocimiento general | Niveles de dificultad",
            True, TEXT_MUTED
        )
        self.screen.blit(subtitle, (self.width // 2 - subtitle.get_width() // 2, ty + 90))

        self.btn_start.draw(self.screen)
        self.btn_settings.draw(self.screen)
        self.btn_quit.draw(self.screen)
        self.btn_update.draw(self.screen)

        # Version y aviso de actualizacion (esquina inferior)
        version_surf = self.font_small.render(
            "v{}".format(APP_VERSION), True, TEXT_MUTED
        )
        self.screen.blit(version_surf, (self.width - version_surf.get_width() - 14,
                                        self.height - version_surf.get_height() - 10))

        st = self.update_info.get("state")
        if st == "ready":
            info = self.update_info.get("info") or {}
            aviso = self.font_small.render(
                "Actualizacion disponible: v{}     (ir a Actualizaciones)".format(
                    info.get("version", "")),
                True, CORRECT_GREEN,
            )
            self.screen.blit(aviso, (14, self.height - aviso.get_height() - 10))
        elif st == "checking":
            aviso = self.font_small.render(
                "Buscando actualizaciones...", True, TEXT_MUTED
            )
            self.screen.blit(aviso, (14, self.height - aviso.get_height() - 10))

        # Mensaje de confirmacion/error de importacion (temporal)
        self._draw_import_message()

    def _draw_import_message(self):
        """Dibuja el aviso temporal de importacion abajo, envuelto si es largo."""
        if not (self.import_message and pygame.time.get_ticks() < self.import_message_until):
            return
        font = self.font_medium
        max_w = max(200, min(self.width - 80, 640))
        # Envolver el texto
        lines, cur = [], ""
        for word in self.import_message.split(" "):
            test = (cur + " " + word).strip()
            if font.render(test, True, self.import_message_color).get_width() > max_w and cur:
                lines.append(cur.rstrip())
                cur = word
            else:
                cur = test
        if cur:
            lines.append(cur.rstrip())
        line_h = font.get_height() + 4
        mbw = max_w + 24
        mbh = 16 + line_h * len(lines)
        mby = 12
        mbx = (self.width - mbw) // 2

        bg = pygame.Surface((mbw, mbh), pygame.SRCALPHA)
        bg.fill((10, 14, 30, 205))
        pygame.draw.rect(bg, (*self.import_message_color, 190), bg.get_rect(), 2, border_radius=8)
        self.screen.blit(bg, (mbx, mby))
        y = mby + 8
        for ln in lines:
            surf = font.render(ln, True, self.import_message_color)
            self.screen.blit(surf, (mbx + 12, y))
            y += line_h

    # -- pantalla de ajustes -------------------------------------------------
    def draw_settings_screen(self):
        self._draw_gradient_bg(self.screen)

        # Fondo de panel
        panel_rect = pygame.Rect(
            int(self.width * 0.05), 64, int(self.width * 0.90), int(self.height * 0.82)
        )
        pygame.draw.rect(self.screen, PANEL, panel_rect, border_radius=12)
        pygame.draw.rect(self.screen, ACCENT, panel_rect, 2, border_radius=12)

        # Titulo
        title = self.font_large.render("Ajustes del Quiz", True, ACCENT)
        self.screen.blit(title, (self.width // 2 - title.get_width() // 2, 30))

        # Etiquetas
        for surf, x, y in self.settings_labels:
            self.screen.blit(surf, (x, y))

        # Inputs
        self.settings_inputs["num_questions"].draw(self.screen)
        for lvl in VALID_LEVELS:
            self.settings_inputs[f"points_{lvl}"].draw(self.screen)
            self.level_checks[lvl].draw(self.screen)
        self.settings_inputs["time_per_question"].draw(self.screen)
        self.chk_all.draw(self.screen)
        self.chk_unlimited.draw(self.screen)

        # Aviso de validacion antes de empezar
        if self.settings_warning:
            warn_surf = self.font_small.render(self.settings_warning, True, WARNING_ORANGE)
            if warn_surf.get_width() > panel_rect.width - 40:
                self._draw_wrapped_text(
                    self.settings_warning, self.font_small, WARNING_ORANGE,
                    panel_rect.x + 20, panel_rect.bottom - 150,
                    panel_rect.width - 40, 60
                )
            else:
                self.screen.blit(
                    warn_surf,
                    (panel_rect.centerx - warn_surf.get_width() // 2, panel_rect.bottom - 145)
                )

        # Botones
        self.btn_back_settings.draw(self.screen)
        self.btn_save.draw(self.screen)
        self.btn_restore.draw(self.screen)
        self.btn_start_quiz.draw(self.screen)

    # -- pantalla de quiz ----------------------------------------------------
    def draw_quiz_screen(self):
        self._draw_gradient_bg(self.screen)
        self._draw_top_bar()
        self._draw_flash_effect()

        q = self.quiz.current_question

        # Nivel de dificultad con color
        level_color = LEVEL_COLORS.get(q.nivel, TEXT_LIGHT)
        level_surf = self.font_small.render(
            f"Nivel: {LEVEL_LABELS.get(q.nivel, q.nivel).upper()}",
            True, level_color
        )
        self.screen.blit(level_surf, (20, int(self.height * 0.13)))

        # Panel de pregunta
        panel_rect = pygame.Rect(
            int(self.width * 0.05), int(self.height * 0.19),
            int(self.width * 0.90), int(self.height * 0.26)
        )
        pygame.draw.rect(self.screen, PANEL, panel_rect, border_radius=12)
        pygame.draw.rect(self.screen, ACCENT, panel_rect, 2, border_radius=12)

        # Texto de pregunta (envuelto)
        self._draw_wrapped_text(q.texto, self.font_question, TEXT_LIGHT,
                                panel_rect.x + 20, panel_rect.y + 18,
                                panel_rect.width - 40, panel_rect.height - 36)

        # Botones de opciones
        labels = ["A", "B", "C", "D"]
        for i, btn in enumerate(self.option_buttons):
            btn.text = f"{labels[i]}. {q.opciones[i]}"
            btn._render()
            btn.draw(self.screen)

        # Boton Siguiente (solo visible despues de responder)
        if self.show_next_button:
            self.btn_next.draw(self.screen)

    def _draw_wrapped_text(self, text, font, color, x, y, max_width, max_height):
        """Dibuja texto envuelto dentro de un rectangulo."""
        words = text.split(" ")
        lines = []
        current_line = ""
        for word in words:
            test_line = current_line + word + " "
            test_surf = font.render(test_line, True, color)
            if test_surf.get_width() > max_width and current_line:
                lines.append(current_line)
                current_line = word + " "
            else:
                current_line = test_line
        if current_line:
            lines.append(current_line)

        # Truncar si hay demasiadas lineas
        y_offset = y
        for line in lines[:max_height // (font.get_height() + 4)]:
            surf = font.render(line, True, color)
            self.screen.blit(surf, (x, y_offset))
            y_offset += font.get_height() + 6

    # -- pantalla de resultados ----------------------------------------------
    def draw_results_screen(self):
        self._draw_gradient_bg(self.screen)

        # Panel principal
        panel_rect = pygame.Rect(
            int(self.width * 0.06), int(self.height * 0.09),
            int(self.width * 0.88), int(self.height * 0.72)
        )
        pygame.draw.rect(self.screen, PANEL, panel_rect, border_radius=12)
        pygame.draw.rect(self.screen, ACCENT, panel_rect, 2, border_radius=12)

        # Titulo
        title = self.font_title.render("Resultado Final", True, ACCENT)
        self.screen.blit(title, (self.width // 2 - title.get_width() // 2, 40))

        summary = self.quiz.get_summary()

        y = panel_rect.y + 40
        cx = self.width // 2

        # Puntaje total
        score_text = self.font_large.render(
            f"Puntaje Total: {summary['score']}", True, ACCENT
        )
        self.screen.blit(score_text, (cx - score_text.get_width() // 2, y))
        y += int(self.height * 0.07)

        # Tiempo total
        time_text = self.font_medium.render(
            f"Tiempo Total: {summary['total_time']:.1f} segundos", True, TEXT_LIGHT
        )
        self.screen.blit(time_text, (cx - time_text.get_width() // 2, y))
        y += int(self.height * 0.055)

        # Promedio por pregunta
        avg_text = self.font_medium.render(
            f"Promedio por pregunta: {summary['tiempo_promedio']:.2f} segundos",
            True, TEXT_LIGHT
        )
        self.screen.blit(avg_text, (cx - avg_text.get_width() // 2, y))
        y += int(self.height * 0.055)

        # Correctas/Incorrectas
        stats_text = self.font_medium.render(
            f"Correctas: {summary['correctas']}  |  Incorrectas: {summary['incorrectas']}",
            True, TEXT_LIGHT
        )
        self.screen.blit(stats_text, (cx - stats_text.get_width() // 2, y))
        y += int(self.height * 0.065)

        # Tabla por nivel
        table_title = self.font_medium.render("Detalles por Nivel", True, TEXT_MUTED)
        self.screen.blit(table_title, (cx - table_title.get_width() // 2, y))
        y += int(self.height * 0.042)

        for lvl in VALID_LEVELS:
            s = summary["stats"][lvl]
            row_surf = self.font_small.render(
                f"{LEVEL_LABELS[lvl]:>16s}: {s['correctas']} correctas, {s['incorrectas']} incorrectas",
                True, LEVEL_COLORS[lvl]
            )
            self.screen.blit(row_surf, (cx - row_surf.get_width() // 2, y))
            y += int(self.height * 0.036)

        # Botones
        self.btn_retry.draw(self.screen)
        self.btn_back_settings_r.draw(self.screen)

    # -- pantalla de error ---------------------------------------------------
    def draw_error_screen(self):
        self._draw_gradient_bg(self.screen)

        panel = pygame.Rect(
            int(self.width * 0.12), self.height // 2 - 100,
            int(self.width * 0.76), 220
        )
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, INCORRECT_RED, panel, 2, border_radius=12)

        title = self.font_large.render("Error", True, INCORRECT_RED)
        self.screen.blit(title, (self.width // 2 - title.get_width() // 2, panel.y - 40))

        self._draw_wrapped_text(
            self.error_message, self.font_medium, TEXT_LIGHT,
            panel.x + 20, panel.y + 25, panel.width - 40, 130
        )

        self.btn_back_to_settings.draw(self.screen)

    # -- main loop -----------------------------------------------------------
    def run(self):
        """Bucle principal del juego."""
        # Sonido de inicio
        self.sounds.play_music_start()
        dt_accumulator = 0.0
        logger.info("Bucle principal iniciado (pantalla=%s)", self.screen_state)

        while self.running:
            dt = self.clock.tick(FPS) / 1000.0  # delta time en segundos
            dt_accumulator += dt

            try:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                        continue

                    if event.type == pygame.VIDEORESIZE:
                        self._on_resize(event.size)
                        continue

                    mx, my = pygame.mouse.get_pos()

                    if self.screen_state == SCREEN_START:
                        self._handle_start_event(event)

                    elif self.screen_state == SCREEN_SETTINGS:
                        self._handle_settings_event(event)

                    elif self.screen_state == SCREEN_QUIZ:
                        self._handle_quiz_event(event)

                    elif self.screen_state == SCREEN_RESULTS:
                        self._handle_results_event(event)

                    elif self.screen_state == SCREEN_ERROR:
                        self._handle_error_event(event)

                    elif self.screen_state == SCREEN_IMPORT:
                        self._handle_import_event(event)

                    elif self.screen_state == SCREEN_UPDATE:
                        self._handle_update_event(event)

                # Actualizaciones continuas
                if self.screen_state == SCREEN_QUIZ and self.quiz:
                    self._update_quiz(dt)

                # Dibujar
                self._draw_current_screen()
            except Exception:
                logger.error("Error en frame:\n%s", traceback.format_exc())
                self.error_message = (
                    "Ocurrio un error. Revisa quiz.log para el detalle y "
                    "vuelve a ajustes."
                )
                self._build_error_screen()
                self.screen_state = SCREEN_ERROR

            pygame.display.flip()

        pygame.quit()
        logger.info("Cerrando aplicacion")
        sys.exit()

    def _on_resize(self, size):
        """Reajusta la ventana y reconstruye el layout de forma dinamica."""
        w, h = size
        w = max(MIN_WIDTH, w)
        h = max(MIN_HEIGHT, h)
        self.width, self.height = w, h
        try:
            self.screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
            self._rebuild_all_ui()
            logger.debug("Ventana redimensionada a %dx%d", w, h)
        except Exception:
            logger.error("Fallo al redimensionar a %sx%s:\n%s",
                         w, h, traceback.format_exc())

    # -- event handlers ------------------------------------------------------
    def _handle_start_event(self, event):
        if self.btn_start.handle_event(event):
            self.sounds.play("click")
            self._open_import_screen()
        if self.btn_settings.handle_event(event):
            self.sounds.play("click")
            self.settings_warning = ""
            self.screen_state = SCREEN_SETTINGS
            logger.info("Abriendo pantalla de ajustes")
        if self.btn_quit.handle_event(event):
            self.running = False

        if self.btn_update.handle_event(event):
            self.sounds.play("click")
            self.screen_state = SCREEN_UPDATE
            logger.info("Abriendo pantalla de actualizaciones")

    def _set_import_message(self, text, ok=True, color=None):
        """Muestra un mensaje de importacion (banner en la pantalla Importar Quiz)."""
        self.import_message = text
        if color is not None:
            self.import_message_color = color
        else:
            self.import_message_color = CORRECT_GREEN if ok else INCORRECT_RED
        self.import_message_until = pygame.time.get_ticks() + 6000

    def _native_file_dialog(self):
        """Abre el selector nativo del sistema en Linux (KDE kdialog / GTK zenity).

        En Windows/Mac tkinter ya usa el explorador nativo, asi que ahi se
        devuelve None para usar el fallback de tkinter. En Linux tkinter siempre
        muestra el dialogo generico de Tk, por eso se prioriza kdialog (KDE,
        mismo explorador que Dolphin) y zenity. Devuelve la ruta elegida, '' si
        se cancelo, o None si no hay herramienta nativa disponible.
        """
        if sys.platform != "linux":
            return None

        start_dir = os.path.expanduser("~")
        candidates = [
            (
                "kdialog",
                [
                    "kdialog", "--title", "Importar preguntas (CSV)",
                    "--getopenfilename", start_dir, "*.csv *.CSV",
                ],
            ),
            (
                "zenity",
                [
                    "zenity", "--file-selection",
                    "--title=Importar preguntas (CSV)",
                    "--file-filter=Archivos CSV (*.csv) | *.csv",
                    "--file-filter=Todos los archivos | *",
                ],
            ),
        ]
        for tool, cmd in candidates:
            if shutil.which(tool):
                try:
                    proc = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=120
                    )
                    path = proc.stdout.strip()
                    logger.info("Selector nativo '%s' devuelto: '%s' (exit=%s)",
                                tool, path, proc.returncode)
                    if not path or proc.returncode != 0:
                        return ""
                    return path
                except Exception as e:
                    logger.warning("Fallo al usar '%s': %s", tool, e)
        return None

    def _pick_csv_path(self):
        """Abre el explorador nativo del sistema. Devuelve la ruta o '' si cancela."""
        path = self._native_file_dialog()

        if path is None:
            # Fallback: dialogo estandar de tkinter (nativo en Windows/Mac,
            # generico en Linux si no hay kdialog/zenity instalados)
            used_generic = sys.platform == "linux"
            try:
                import tkinter as tk
                from tkinter import filedialog
            except Exception as e:
                logger.error("tkinter no disponible: %s", e)
                self._set_import_message(
                    "El selector de archivos no esta disponible en este sistema.",
                    ok=False,
                )
                return ""

            root = None
            try:
                root = tk.Tk()
                root.withdraw()   # ocultar la ventana raiz ANTES de abrir el dialogo
                root.update()     # asegurar que la raiz quede correctamente inicializada
                try:
                    root.attributes("-topmost", True)  # el dialogo se abre sobre el juego
                except Exception:
                    pass
                path = filedialog.askopenfilename(
                    title="Importar preguntas (CSV)",
                    parent=root,
                    filetypes=[("Archivos CSV", "*.csv"), ("Todos los archivos", "*.*")],
                )
            except Exception as e:
                logger.error("Fallo al abrir el selector de archivos: %s", e)
                self._set_import_message("No se pudo abrir el selector de archivos.", ok=False)
                return ""
            finally:
                if root is not None:
                    try:
                        root.destroy()  # cerrar Tk por completo (sin ventanas fantasma)
                    except Exception:
                        pass
            if not path and used_generic:
                self._set_import_message(
                    "Dialogo generico: instala 'kdialog' o 'zenity' para usar "
                    "el explorador nativo del sistema.",
                    ok=False,
                )

        # Devolver el foco a la ventana de Pygame en todos los caminos
        self._regain_pygame_focus()

        return (path or "").strip()

    def _handle_import_new(self):
        """'Importar nuevo CSV': elige archivo, lo copia al banco y avisa."""
        path = self._pick_csv_path()
        if not path:
            logger.info("Importacion cancelada por el usuario")
            return
        self._import_csv_to_bank(path)

    def _import_csv_to_bank(self, path):
        """Valida el CSV, lo copia a csv/<fecha>/ y muestra el resumen."""
        try:
            questions, skipped = QuestionLoader.load_lenient(path)
        except Exception as e:
            logger.error("CSV invalido (%s): %s", path, e)
            self._set_import_message(f"Archivo invalido: {e}", ok=False)
            return

        if not questions:
            self._set_import_message("El archivo no contiene preguntas validas.", ok=False)
            return

        try:
            copied = import_csv_to_bank(path)
        except Exception as e:
            logger.error("No se pudo guardar la copia en csv/: %s", e)
            self._set_import_message(
                f"No se pudo guardar la copia en la carpeta csv/: {e}", ok=False
            )
            return

        # Resumen con desglose por nivel
        per = {lvl: sum(1 for q in questions if q.nivel == lvl) for lvl in VALID_LEVELS}
        partes = " | ".join(f"{LEVEL_LABELS[l]}: {per[l]}" for l in VALID_LEVELS)
        msg = f"✓ {len(questions)} preguntas detectadas — {partes}"
        if skipped:
            msg += f" — ⚠ {skipped} filas ignoradas por formato incorrecto"

        self._set_import_message(
            msg,
            ok=(skipped == 0),
            color=(WARNING_ORANGE if skipped else CORRECT_GREEN),
        )
        self.import_sessions = list_sessions()
        self.import_scroll = 0
        logger.info("Importadas %d preguntas (%s) -> %s [ignoradas=%d]",
                    len(questions), path, copied, skipped)

    def _regain_pygame_focus(self):
        """Devuelve el foco a la ventana de Pygame tras cerrar el dialogo Tk."""
        try:
            self.screen = pygame.display.set_mode(
                (self.width, self.height), pygame.RESIZABLE
            )
        except Exception as e:
            logger.warning("No se pudo devolver el foco a Pygame: %s", e)

    # -- pantalla de importacion ---------------------------------------------
    IMPORT_ROW_H = 86
    IMPORT_ROW_MARGIN = 12

    def _open_import_screen(self):
        """Entra a la pantalla 'Importar Quiz' leyendo las sesiones guardadas."""
        self.import_sessions = list_sessions()
        self.import_scroll = 0
        self._build_import_screen()
        self.screen_state = SCREEN_IMPORT
        logger.info("Abriendo pantalla de importacion (%d sesiones)",
                    len(self.import_sessions))

    def _build_import_screen(self):
        """Crea los elementos interactivos de la pantalla 'Importar Quiz'."""
        w, h = self.width, self.height
        panel = pygame.Rect(int(w * 0.06), 58, int(w * 0.88), int(h * 0.82))
        self.panel_import = panel
        self.btn_import_back = Button(
            (24, 18, 120, 42), "Volver", self.font_medium
        )
        self.btn_import_new = Button(
            (panel.x + 30, panel.y + 24, min(300, panel.width - 60), 48),
            "Importar nuevo CSV", self.font_medium
        )
        self.import_scroll = max(
            0, min(self.import_scroll, self._import_max_scroll())
        )

    def _build_update_screen(self):
        """Crea los elementos interactivos de la pantalla de actualizaciones."""
        w, h = self.width, self.height
        self.btn_update_back = Button(
            (24, 18, 120, 42), "Volver", self.font_medium
        )
        btn_w, btn_h = 240, 48
        self.btn_update_refresh = Button(
            (w // 2 - btn_w - 20, h - 100, btn_w, btn_h),
            "Buscar ahora", self.font_medium
        )
        self.btn_update_apply = Button(
            (w // 2 + 20, h - 100, btn_w, btn_h),
            "Descargar e instalar", self.font_medium
        )

    def _import_max_scroll(self):
        """Desplazamiento maximo de la lista (0 si cabe entera)."""
        list_rect = self._import_layout()["list_rect"]
        content = (
            len(self.import_sessions) * (self.IMPORT_ROW_H + self.IMPORT_ROW_MARGIN)
            - self.IMPORT_ROW_MARGIN
        )
        return max(0, content - list_rect.height)

    def _import_layout(self):
        """Posiciones calculadas de la pantalla (banner, lista, botones)."""
        panel = self.panel_import
        banner_h = 0
        if self.import_message:
            font = self.font_medium
            maxw = panel.width - 160
            lines = 1
            cur = ""
            for word in self.import_message.split(" "):
                test = (cur + " " + word).strip()
                if font.render(test, True, (255, 255, 255)).get_width() > maxw and cur:
                    lines += 1
                    cur = word
                else:
                    cur = test
            banner_h = 14 + (font.get_height() + 4) * lines
        new_btn = self.btn_import_new.rect
        section_y = new_btn.bottom + 14 + banner_h + 8
        list_y = section_y + 36
        list_bottom = panel.bottom - 20
        if list_bottom - list_y < 20:
            list_bottom = list_y + 20
        list_rect = pygame.Rect(
            panel.x + 24, list_y, panel.width - 48, list_bottom - list_y
        )
        return {
            "panel": panel,
            "section_y": section_y,
            "list_rect": list_rect,
            "banner_h": banner_h,
        }

    def _import_rows(self, layout):
        """Devuelve [(indice, sesion, rect_fila, rect_usar)] visibles."""
        rows = []
        lr = layout["list_rect"]
        row_h, margin = self.IMPORT_ROW_H, self.IMPORT_ROW_MARGIN
        for i, sess in enumerate(self.import_sessions):
            y = lr.y - self.import_scroll + i * (row_h + margin)
            if y + row_h < lr.y - 2 or y > lr.bottom + 2:
                continue
            row = pygame.Rect(lr.x, y, lr.width, row_h)
            use_rect = pygame.Rect(
                row.right - 190, row.y + (row_h - 44) // 2, 172, 44
            )
            rows.append((i, sess, row, use_rect))
        return rows

    def draw_import_screen(self):
        self._draw_gradient_bg(self.screen)
        layout = self._import_layout()
        panel = layout["panel"]

        pygame.draw.rect(self.screen, PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, ACCENT, panel, 2, border_radius=12)

        title = self.font_title.render("Importar Quiz", True, ACCENT)
        self.screen.blit(title, (self.width // 2 - title.get_width() // 2, 28))

        self.btn_import_back.draw(self.screen)
        self.btn_import_new.draw(self.screen)

        self._draw_import_banner(layout)

        sec = self.font_medium.render("Sesiones anteriores", True, ACCENT)
        self.screen.blit(sec, (panel.x + 30, layout["section_y"]))

        if not self.import_sessions:
            self._draw_import_empty(layout["list_rect"])
        else:
            self._draw_import_list(layout)

    def draw_update_screen(self):
        self._draw_gradient_bg(self.screen)

        panel_rect = pygame.Rect(
            int(self.width * 0.06), 64, int(self.width * 0.88), int(self.height * 0.80)
        )
        pygame.draw.rect(self.screen, PANEL, panel_rect, border_radius=12)
        pygame.draw.rect(self.screen, ACCENT, panel_rect, 2, border_radius=12)

        title = self.font_title.render("Actualizaciones", True, ACCENT)
        self.screen.blit(title, (self.width // 2 - title.get_width() // 2, 30))

        # Version instalada
        ver_surf = self.font_medium.render(
            "Version instalada: v{}".format(APP_VERSION), True, TEXT_LIGHT
        )
        self.screen.blit(ver_surf, (panel_rect.x + 30, panel_rect.y + 32))

        state = self.update_info.get("state", "checking")
        x = panel_rect.x + 30
        y = panel_rect.y + 90
        max_w = panel_rect.width - 60

        if state == "checking":
            txt = "Buscando actualizaciones en GitHub..."
            self._draw_wrapped_text(txt, self.font_medium, TEXT_MUTED, x, y, max_w, 60)
        elif state == "ok":
            ok = self.font_medium.render(
                "Ya tienes la ultima version. :) No hay nada que actualizar.",
                True, CORRECT_GREEN,
            )
            self.screen.blit(ok, (x, y))
        elif state == "error":
            err = self.font_medium.render(
                "No se pudo comprobar actualizaciones.", True, INCORRECT_RED
            )
            self.screen.blit(err, (x, y))
            self._draw_wrapped_text(
                self.update_info.get("error", ""), self.font_small,
                TEXT_MUTED, x, y + 34, max_w, 90,
            )
            hint = self.font_small.render(
                "Comprueba tu conexion a internet y reintenta.", True, TEXT_MUTED
            )
            self.screen.blit(hint, (x, y + 130))
        elif state in ("ready", "applying", "applied"):
            info = self.update_info.get("info") or {}
            v = info.get("version") or ""
            nuevo = self.font_large.render(
                "Nueva version disponible: v{}".format(v), True, ACCENT
            )
            self.screen.blit(nuevo, (x, y))
            y += 50
            notas = (info.get("notas") or "").strip() or "Sin descripcion."
            self._draw_wrapped_text(
                "Notas del release:", self.font_medium, TEXT_LIGHT, x, y, max_w, 80,
            )
            y += 40
            self._draw_wrapped_text(notas, self.font_small, TEXT_MUTED, x, y, max_w, 200)

            if state == "applying":
                self._draw_wrapped_text(
                    "Descargando e instalando... no cierres la aplicacion.",
                    self.font_medium, WARNING_ORANGE, x, panel_rect.bottom - 110,
                    max_w, 60,
                )
            elif state == "applied":
                self._draw_wrapped_text(
                    self.update_info.get("applied", ""), self.font_medium,
                    CORRECT_GREEN, x, panel_rect.bottom - 110, max_w, 90,
                )

        # Estado del boton de instalar
        self.btn_update_apply.enabled = (state == "ready")

        self.btn_update_back.draw(self.screen)
        self.btn_update_refresh.draw(self.screen)
        self.btn_update_apply.draw(self.screen)

    def _draw_import_banner(self, layout):
        """Banner persistente con el resultado de la ultima importacion."""
        if not self.import_message:
            return
        font = self.font_medium
        color = self.import_message_color
        maxw = layout["panel"].width - 160
        words = self.import_message.split(" ")
        lines, cur = [], ""
        for word in words:
            test = (cur + " " + word).strip()
            if font.render(test, True, color).get_width() > maxw and cur:
                lines.append(cur.rstrip())
                cur = word
            else:
                cur = test
        if cur:
            lines.append(cur.rstrip())

        lh = font.get_height() + 4
        bw = max(font.render(ln, True, color).get_width() for ln in lines) + 32
        bh = 14 + lh * len(lines)
        bx = layout["panel"].x + (layout["panel"].width - bw) // 2
        by = self.btn_import_new.rect.bottom + 10

        bg = pygame.Surface((bw, bh), pygame.SRCALPHA)
        bg.fill((10, 14, 30, 210))
        pygame.draw.rect(bg, (*color, 200), bg.get_rect(), 2, border_radius=8)
        self.screen.blit(bg, (bx, by))
        y = by + 7
        for ln in lines:
            surf = font.render(ln, True, color)
            self.screen.blit(surf, (bx + 16, y))
            y += lh

    def _draw_import_empty(self, list_rect):
        """Mensaje amigable cuando no hay ninguna sesion importada."""
        cy = list_rect.y + list_rect.height // 2
        # Icono de carpeta dibujado (estilo espacial, sin depender de emojis)
        folder = pygame.Rect(0, 0, 64, 48)
        folder.center = (list_rect.centerx, cy - 46)
        pygame.draw.rect(self.screen, ACCENT, folder, border_radius=6)
        tab = pygame.Rect(folder.x, folder.y, 24, 10)
        pygame.draw.rect(self.screen, ACCENT, tab, border_radius=4)
        pygame.draw.rect(self.screen, PANEL, folder.inflate(-8, -8), border_radius=5)

        msg1 = self.font_large.render(
            "No se han encontrado Quizes.", True, TEXT_LIGHT
        )
        self.screen.blit(
            msg1, (list_rect.centerx - msg1.get_width() // 2, cy - 12)
        )
        msg2 = self.font_medium.render(
            "Importa uno para comenzar a aprender.", True, TEXT_MUTED
        )
        self.screen.blit(
            msg2, (list_rect.centerx - msg2.get_width() // 2, cy + 26)
        )

    def _draw_import_list(self, layout):
        """Dibuja las tarjetas de sesiones anteriores con scroll."""
        lr = layout["list_rect"]
        rows = self._import_rows(layout)
        mouse = pygame.mouse.get_pos()

        for _, sess, row, use_rect in rows:
            hover = sess["valid"] and row.collidepoint(mouse)
            card = (52, 66, 106) if hover else (42, 54, 92)
            pygame.draw.rect(self.screen, card, row, border_radius=10)
            border = ACCENT if hover else (62, 76, 118)
            pygame.draw.rect(self.screen, border, row, 2, border_radius=10)

            # Nombre del archivo (truncado si es muy largo)
            max_name_w = row.width - 210
            name = sess["filename"]
            while (self.font_medium.render(name, True, (0, 0, 0)).get_width()
                   > max_name_w and len(name) > 4):
                name = name[:-4] + "..."
            name_surf = self.font_medium.render(name, True, TEXT_LIGHT)
            self.screen.blit(name_surf, (row.x + 18, row.y + 14))

            date_surf = self.font_small.render(
                sess["date_label"], True, TEXT_MUTED
            )
            self.screen.blit(date_surf, (row.x + 18, row.y + 46))

            # Cantidad de preguntas o indicador de archivo invalido
            if sess["valid"]:
                count_surf = self.font_small.render(
                    f"{sess['num_questions']} preguntas", True, CORRECT_GREEN
                )
                self.screen.blit(count_surf, (row.x + 18, row.y + 66))
                self._draw_use_button(use_rect, mouse)
            else:
                self._draw_warning_icon(row.x + 18, row.y + 62)
                inv_surf = self.font_small.render(
                    "Archivo invalido", True, INCORRECT_RED
                )
                self.screen.blit(inv_surf, (row.x + 44, row.y + 60))

        # Barra de scroll si hay mas sesiones que las que caben
        content = (
            len(self.import_sessions) * (self.IMPORT_ROW_H + self.IMPORT_ROW_MARGIN)
            - self.IMPORT_ROW_MARGIN
        )
        if content > lr.height:
            track = pygame.Rect(lr.right + 4, lr.y, 6, lr.height)
            pygame.draw.rect(self.screen, (50, 60, 90), track, border_radius=3)
            knob_h = max(24, int(lr.height * lr.height / content))
            knob_y = lr.y + int(
                (lr.height - knob_h) * self.import_scroll
                / max(1, content - lr.height)
            )
            knob = pygame.Rect(track.x, knob_y, 6, knob_h)
            pygame.draw.rect(self.screen, ACCENT, knob, border_radius=3)

    def _draw_use_button(self, rect, mouse):
        """Boton 'Usar este Quiz' de una tarjeta."""
        hover = rect.collidepoint(mouse)
        color = BUTTON_HOVER if hover else BUTTON
        pygame.draw.rect(self.screen, color, rect, border_radius=8)
        pygame.draw.rect(self.screen, ACCENT, rect, 2, border_radius=8)
        label = self.font_small.render("Usar este Quiz", True, TEXT_LIGHT)
        rect_l = label.get_rect(center=rect.center)
        self.screen.blit(label, rect_l)

    def _draw_warning_icon(self, x, cy):
        """Triangulo de advertencia (estilo espacial, sin emojis)."""
        size = 14
        pts = [(x + size // 2, cy - size), (x, cy + size - 4), (x + size, cy + size - 4)]
        pygame.draw.polygon(self.screen, INCORRECT_RED, pts)
        ex = self.font_small.render("!", True, TEXT_LIGHT)
        ex = pygame.transform.smoothscale(ex, (10, 10))
        self.screen.blit(ex, (x + size // 2 - 5, cy - 5))

    def _handle_import_event(self, event):
        if self.btn_import_back.handle_event(event):
            self.sounds.play("click")
            self.screen_state = SCREEN_START
            logger.info("Volviendo al inicio desde la pantalla de importacion")
            return

        if self.btn_import_new.handle_event(event):
            self.sounds.play("click")
            self._handle_import_new()
            return

        if event.type == pygame.MOUSEWHEEL:
            list_rect = self._import_layout()["list_rect"]
            if list_rect.collidepoint(pygame.mouse.get_pos()):
                self.import_scroll = max(
                    0,
                    min(
                        self._import_max_scroll(),
                        self.import_scroll - event.y * 60,
                    ),
                )
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            layout = self._import_layout()
            for idx, sess, row, _ in self._import_rows(layout):
                if sess["valid"] and row.collidepoint(event.pos):
                    self.sounds.play("click")
                    self._use_import_session(idx)
                    return

    def _use_import_session(self, idx):
        """Activa un CSV de sesiones anteriores y va a los ajustes."""
        sess = self.import_sessions[idx]
        if not sess["valid"]:
            logger.warning("Sesion invalida, no seleccionable: %s", sess["path"])
            return
        self.settings.question_file = sess["path"]
        self.settings.save()
        self.import_message = ""
        self.settings_warning = ""
        self.screen_state = SCREEN_SETTINGS
        logger.info("Usando banco de preguntas: %s (%d preguntas)",
                    sess["filename"], sess["num_questions"])

    def _start_update_check(self):
        """Comprueba en segundo plano si hay una version nueva en GitHub."""
        self.update_info = {
            "state": "checking", "info": None, "error": "", "applied": "",
        }

        def work():
            try:
                info = updater_mod.check_for_update()
                self.update_info["state"] = "ready" if info else "ok"
                self.update_info["info"] = info
            except Exception as exc:
                logger.warning("Fallo al buscar actualizaciones: %s", exc)
                self.update_info["state"] = "error"
                self.update_info["error"] = str(exc)

        threading.Thread(target=work, daemon=True).start()

    def _start_update_apply(self):
        """Descarga e instala la actualizacion en segundo plano."""
        info = self.update_info.get("info")
        if not info:
            return
        self.update_info["state"] = "applying"
        self.update_info["applied"] = ""
        zip_url = info["url"]
        new_version = info["version"]

        def work():
            try:
                ver, msg = updater_mod.apply_update(zip_url, new_version)
                logger.info("Actualizacion aplicada a v%s", ver)
                self.update_info["state"] = "applied"
                self.update_info["applied"] = msg
                self.update_info["info"] = None
            except Exception as exc:
                logger.error("Error al aplicar la actualizacion:\n%s",
                             traceback.format_exc())
                self.update_info["state"] = "error"
                self.update_info["error"] = "Error al actualizar: {}".format(exc)

        threading.Thread(target=work, daemon=True).start()

    def _handle_update_event(self, event):
        if self.btn_update_back.handle_event(event):
            self.sounds.play("click")
            self.screen_state = SCREEN_START
            logger.info("Volviendo al inicio desde actualizaciones")
            return
        if self.btn_update_refresh.handle_event(event):
            self.sounds.play("click")
            self._start_update_check()
            return
        st = self.update_info.get("state")
        if self.btn_update_apply.handle_event(event) and st == "ready":
            self.sounds.play("click")
            self._start_update_apply()

    def _handle_settings_event(self, event):
        # Inputs
        for inp in self.settings_inputs.values():
            inp.handle_event(event)

        self.chk_unlimited.handle_event(event)

        # Checkboxes de nivel
        changed = False
        for lvl in VALID_LEVELS:
            if self.level_checks[lvl].handle_event(event):
                changed = True
        if changed:
            self.chk_all.checked = all(
                self.level_checks[lvl].checked for lvl in VALID_LEVELS
            )

        if self.chk_all.handle_event(event):
            val = self.chk_all.checked
            for lvl in VALID_LEVELS:
                self.level_checks[lvl].checked = val

        if self.btn_back_settings.handle_event(event):
            self.sounds.play("click")
            self.settings_warning = ""
            self.screen_state = SCREEN_START
            logger.info("Volviendo a la pantalla de inicio (sin guardar)")

        if self.btn_save.handle_event(event):
            self.sounds.play("click")
            self.settings_warning = ""
            self._apply_settings_from_inputs()
            logger.info("Configuracion guardada: %s", self.settings.as_dict)

        if self.btn_restore.handle_event(event):
            self.sounds.play("click")
            self.settings_warning = ""
            self.settings.restore_defaults()
            self._refresh_settings_inputs()
            logger.info("Configuracion restaurada a valores por defecto")

        if self.btn_start_quiz.handle_event(event):
            self.sounds.play("click")
            self._start_quiz_from_settings()

    def _handle_quiz_event(self, event):
        if self.show_next_button and self.btn_next.handle_event(event):
            self.sounds.play("click")
            self._next_question()
            return

        # No permitir responder durante flash/fade o si ya respondio
        if self.show_next_button:
            return
        if self.flash_timer > 0 or self.fade_alpha > 0:
            return

        for btn in self.option_buttons:
            if btn.handle_event(event):
                self.sounds.play("click")
                q = self.quiz.current_question
                selected = q.opciones[btn.index]
                time_used = self.quiz.question_time
                is_correct = self.quiz.answer(selected, time_used)
                logger.debug(
                    "Respuesta en pregunta %d/%d: %s en %.2fs (%s)",
                    self.quiz.question_number, self.quiz.num_questions,
                    "correcta" if is_correct else "incorrecta",
                    time_used, q.nivel,
                )
                if is_correct:
                    self.flash_color = CORRECT_GREEN
                    self.sounds.play("correct")
                else:
                    self.flash_color = INCORRECT_RED
                    self.sounds.play("error")
                self.flash_timer = self.flash_duration
                self.show_next_button = True

    def _handle_results_event(self, event):
        if self.btn_retry.handle_event(event):
            self.sounds.play("click")
            self._start_quiz()
        if self.btn_back_settings_r.handle_event(event):
            self.sounds.play("click")
            self.screen_state = SCREEN_SETTINGS

    def _handle_error_event(self, event):
        if self.btn_back_to_settings.handle_event(event):
            self.sounds.play("click")
            self.screen_state = SCREEN_SETTINGS

    # -- lógica de juego -----------------------------------------------------
    def _apply_settings_from_inputs(self):
        """Lee los valores de los InputBox/checkboxes y actualiza Settings."""
        nq = self.settings_inputs["num_questions"].value
        if nq is not None and 4 <= nq <= 100:
            self.settings.num_questions = nq

        for lvl in VALID_LEVELS:
            val = self.settings_inputs[f"points_{lvl}"].value
            if val is not None and val >= 0:
                self.settings.points[lvl] = int(val)

        t = self.settings_inputs["time_per_question"].value
        if t is not None and t > 0:
            self.settings.time_per_question = t

        self.settings.unlimited_time = self.chk_unlimited.checked

        # Niveles seleccionados (al menos uno)
        selected = [lvl for lvl in VALID_LEVELS if self.level_checks[lvl].checked]
        if not selected:
            for lvl in VALID_LEVELS:
                self.level_checks[lvl].checked = True
            self.chk_all.checked = True
            selected = list(VALID_LEVELS)
        self.settings.levels = selected

        self.settings.save()

    def _prepare_questions(self):
        """Carga y filtra las preguntas segun la configuracion actual."""
        qfile = self.settings.question_file
        if os.path.isabs(qfile):
            filepath = qfile
        else:
            filepath = os.path.join(data_dir(), qfile)
        if not os.path.exists(filepath):
            filepath = os.path.join(resource_dir(), "questions.csv")
        try:
            all_questions, _ = QuestionLoader.load_lenient(filepath)
        except Exception as e:
            logger.error("No se pudieron cargar las preguntas de %s: %s",
                         filepath, e)
            return None, str(e)

        total = len(all_questions)
        levels = set(self.settings.levels)
        all_questions = [q for q in all_questions if q.nivel in levels]
        logger.debug("Preguntas: %d totales en %s, %d para niveles %s",
                     total, filepath, len(all_questions), levels)
        if not all_questions:
            return None, "No hay preguntas disponibles para los niveles seleccionados."
        return all_questions, None

    def _start_quiz_from_settings(self):
        """Valida que haya suficientes preguntas antes de comenzar desde ajustes."""
        self._apply_settings_from_inputs()

        all_questions, err = self._prepare_questions()
        if err:
            self.settings_warning = err
            self.sounds.play("error")
            return

        if len(all_questions) < self.settings.num_questions:
            per = {
                lvl: sum(1 for q in all_questions if q.nivel == lvl)
                for lvl in VALID_LEVELS
            }
            partes = " | ".join(
                f"{LEVEL_LABELS[l]}: {per[l]}" for l in VALID_LEVELS
            )
            self.settings_warning = (
                f"Insuficientes preguntas: hay {len(all_questions)} para los "
                f"niveles elegidos y pides {self.settings.num_questions}. "
                f"Disponibles {partes}."
            )
            self.sounds.play("error")
            return

        self.settings_warning = ""
        self._start_quiz(all_questions)

    def _start_quiz(self, all_questions=None):
        """Inicia una nueva partida, cargando preguntas segun configuracion."""
        if all_questions is None:
            all_questions, err = self._prepare_questions()
            if err:
                self.error_message = err
                self._build_error_screen()
                self.screen_state = SCREEN_ERROR
                return

        if len(all_questions) < self.settings.num_questions:
            logger.warning(
                "Preguntas insuficientes: disponibles=%d pedidas=%d",
                len(all_questions), self.settings.num_questions,
            )
            self.error_message = (
                f"Solo hay {len(all_questions)} preguntas disponibles para los "
                f"niveles seleccionados y se pidieron {self.settings.num_questions}. "
                f"Revise la configuracion en los ajustes."
            )
            self._build_error_screen()
            self.screen_state = SCREEN_ERROR
            return

        self.sounds.play("start")
        self.quiz = Quiz(all_questions, self.settings.as_dict)
        self._build_quiz_ui()
        logger.info(
            "Quiz iniciado: %d preguntas (niveles=%s) puntos=%s tiempo=%s ilimitado=%s",
            self.quiz.num_questions, self.settings.levels,
            self.settings.points, self.settings.time_per_question,
            self.settings.unlimited_time,
        )

        # Resetear animaciones
        self.fade_alpha = 0
        self.fade_direction = 0
        self.pending_next = False
        self.flash_color = None
        self.flash_timer = 0
        self.show_next_button = False

        self.screen_state = SCREEN_QUIZ

    def _next_question(self):
        """Inicia la transicion de pregunta: fade out, avanza, fade in.

        No avanza la pregunta de inmediato: primero el negro cubre la pregunta
        respondida y, ya a negro total, se avanza en el bucle de actualizacion
        para que la animacion coincida con el momento del clic.
        """
        self.show_next_button = False
        self.pending_next = True
        self.fade_alpha = 0
        self.fade_direction = +1  # fade out (a negro) sobre la pregunta actual

    def _update_quiz(self, dt):
        """Actualiza cronometro, animaciones y estado del quiz."""
        # Actualizar flash
        if self.flash_timer > 0:
            self.flash_timer -= dt
            if self.flash_timer <= 0:
                self.flash_color = None

        # Transicion (fade out -> [avanza de pregunta] -> fade in).
        # Durante el fade no se descuenta el cronometro (pausa de transicion).
        if self.fade_direction != 0:
            self.fade_alpha += self.fade_direction * self.fade_speed * dt
            if self.fade_alpha >= 255:
                # Negro total alcanzado: aqui (y solo aqui) se avanza de pregunta
                if self.pending_next:
                    self.pending_next = False
                    self.quiz.next_question()
                    if self.quiz.game_over:
                        self.fade_alpha = 0
                        self.fade_direction = 0
                        logger.info("Quiz terminado. Resumen: %s",
                                    self.quiz.get_summary())
                        self.sounds.play("celebration")
                        self._build_results_screen()
                        self.screen_state = SCREEN_RESULTS
                        return
                self.fade_alpha = 255
                self.fade_direction = -1  # fade in: alpha baja hasta 0
            elif self.fade_alpha <= 0:
                self.fade_alpha = 0
                self.fade_direction = 0
                self.quiz.time_remaining = (
                    self.quiz.time_per_question if not self.quiz.unlimited_time else None
                )
                self.quiz.question_time = 0.0
        else:
            # Cronometro normal (solo cuando no hay transicion)
            before = self.quiz.answer_result
            self.quiz.update_timer(dt)
            # Si el tiempo se agoto automaticamente -> respuesta incorrecta
            if self.quiz.answer_result and self.quiz.answer_result is not before:
                self.flash_color = INCORRECT_RED
                self.sounds.play("error")
                self.flash_timer = self.flash_duration
                self.show_next_button = True

    def _draw_current_screen(self):
        """Dibuja la pantalla segun el estado actual."""
        if self.screen_state == SCREEN_START:
            self.draw_start_screen()
        elif self.screen_state == SCREEN_SETTINGS:
            self.draw_settings_screen()
        elif self.screen_state == SCREEN_QUIZ:
            self.draw_quiz_screen()
        elif self.screen_state == SCREEN_RESULTS:
            self.draw_results_screen()
        elif self.screen_state == SCREEN_ERROR:
            self.draw_error_screen()
        elif self.screen_state == SCREEN_IMPORT:
            self.draw_import_screen()
        elif self.screen_state == SCREEN_UPDATE:
            self.draw_update_screen()

        self._draw_fade()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    """Inicializa y ejecuta el juego."""
    game = Game()
    game.run()


if __name__ == "__main__":
    main()
