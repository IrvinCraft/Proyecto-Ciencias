# CLAUDE.md — Contexto del proyecto: Quiz Educativo

Aplicación de quiz educativo en Python + Pygame (ventana redimensionable,
animaciones espaciales, sonidos). Banco de preguntas importable desde CSV.

## Cómo ejecutar

```
python3 main.py            # ejecucion normal (terminal: INFO)
python3 main.py --debug    # detalle por fila CSV rechazada al importar
```

El log completo (DEBUG) siempre va a `data_dir()/quiz.log`. Con `--debug`
la terminal muestra además cada fila de CSV ignorada con el motivo exacto
(siempre se guardan en quiz.log, aunque no se use `--debug`).

Requiere `pygame` (ver `requirements.txt`). No hay tests configurados; se
verifican cambios con `python3 -m py_compile <archivo>` y pruebas ad hoc.

## Estructura

- `main.py` — Punto de entrada. Toda la UI (PyGame): `Game`, `Button`,
  `InputBox`, `Checkbox`, `SoundManager`, `SpaceBackground` (fondo animado).
- `quiz_logic.py` — Lógica pura sin Pygame: `Question`, `QuestionLoader`
  (CSV/JSON), `Quiz` (estado, puntaje, cronómetro, stats por nivel).
- `settings.py` — `Settings`: carga/guarda `config.json` (sin Pygame).
- `question_bank.py` — Importa CSVs a `csv/<fecha>/` y lista "sesiones".
- `paths.py` — Resuelve rutas en modo fuente vs compilado (.exe).
  `resource_dir()` = datos solo lectura (assets/, banco por defecto);
  `data_dir()` = datos del usuario (config, csv/, quiz.log):
  - fuente: carpeta del proyecto;
  - exe: `%APPDATA%/QuizEducativo` (Windows) o `~/.quiz_educativo` (Linux/mac).
- `updater.py` — Sistema de actualizaciones vía GitHub Releases (solo stdlib).
  `VERSION` aquí es la versión de la app.
- `generate_sounds.py` — Utilidad dev para regenerar los `.wav` de assets/sounds.
- `assets/sounds/*.wav` — Efectos: click, start, error, correct, celebration.

## Pantallas / estados

`SCREEN_START`, `SCREEN_SETTINGS`, `SCREEN_QUIZ`, `SCREEN_RESULTS`,
`SCREEN_ERROR`, `SCREEN_IMPORT`, `SCREEN_UPDATE`.

Flujo: Inicio → (Comenzar Quiz / Importar / Ajustes / Actualizaciones / Salir).
En Ajustes se configura número de preguntas, niveles, puntos y tiempo.
Al comenzar se entra a `SCREEN_QUIZ`.

## Flujo clave: respuesta y transición de pregunta

- Responder → `Quiz.answer()`, flash verde/rojo, `show_next_button = True`.
- "Siguiente" → `_next_question()`: solo marca `pending_next=True` y `fade_direction=+1`.
  **IMPORTANTE:** la pregunta NO avanza ahí. `_update_quiz()` ejecuta el fade:
  1) fade out a negro, 2) al llegar a `fade_alpha >= 255` avanza con
  `quiz.next_question()` (o termina y va a resultados), 3) fade in revela.
  No rompas esta secuencia: la animación debe empezar en el clic y el avance
  ocurrir dentro del negro.
- Durante el fade no corre el cronómetro (`fade_direction != 0`).

## Configuración (config.json)

`num_questions`, `levels`, `points{ facil,media,dificil,ultra_dificil }`,
`time_per_question`, `unlimited_time`, `question_file` (ruta del CSV, puede ser
absoluta de una sesión importada o relativa → se resuelve contra `data_dir()`).

Niveles válidos: `facil, media, dificil, ultra_dificil`.

## Progreso guardado (progress.json)

- `data_dir()/progress.json` guarda un quiz a medio terminar: orden de
  preguntas, índice actual, puntaje, stats, rachas, tiempo y `answer_result`.
- "Guardar y salir" (modal de Salir) escribe el archivo y vuelve a SCREEN_START;
  "Salir sin guardar" sale sin persistir. Botón X o ESC cierran el modal.
- SCREEN_START muestra "Continuar quiz guardado" mientras exista el archivo.
- Se borra al terminar el quiz (results) y al iniciar uno nuevo.
- Lógica en `quiz_logic.py`: `save_progress`, `load_progress`, `clear_progress`,
  `resume_quiz`. `resume_quiz` respeta el orden guardado (no re-baraja).

## Sistema de actualizaciones (updater.py)

- `check_for_update()` consulta `releases/latest` del repo GitHub y compara
  semver contra `VERSION`. Devuelve dict o None (siempre actualizado / sin
  releases), lanza `UpdateError` si no hay red.
- `apply_update()` descarga el zip del tag y copia sobre el proyecto
  PRESERVANDO: `config.json`, `csv/`, `questions.csv/json`, `quiz.log`,
  `__pycache__`, `.git`.
- En modo compilado (.exe) `apply_update()` lanza `UpdateError`: el exe no se
  auto-reemplaza en marcha; se indica descargar el nuevo desde GitHub Releases.
- Usa el token de `gh` (`~/.config/gh/hosts.yml` o `%APPDATA%/GitHub CLI`) si
  existe (necesario si el repo fuera privado; ahora es público).

## Release / build del .exe

`.github/workflows/build-exe.yml` compila en `windows-latest` con PyInstaller
(`--onefile`, py3.12) cuando se pushea un tag `v*`, inyecta la versión del tag
en `updater.py` y sube `QuizEducativo.exe` al release de ese tag.

Publicar una versión:

```
git tag v1.0.1 && git push origin v1.0.1
```

El workflow crea el release y las notas automáticamente.

## Convenciones

- Código y log en español; names ASCII (sin tildes/ñ) en identificadores.
- Logging con `logging.basicConfig` a `data_dir()/quiz.log` y stdout.
- No hay dependencias "extra": el updater y paths usan solo stdlib.
- `.gitignore` excluye; `.codegraph/`, `build/`, `dist/`, `quiz.log`, etc.

## Repo

GitHub: `IrvinCraft/Proyecto-Ciencias` (público). Detección de estructuras del
código disponible vía CodeGraph (`.codegraph/`).