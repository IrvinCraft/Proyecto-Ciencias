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
  El lector CSV es tolerante: detecta codificación (utf-8/cp1252/latin-1),
  delimitador (`,` `;` tab), variantes de encabezados (`opcion B`, `opción b`,
  `Clave de respuesta correcta`) y acepta la respuesta como letra o texto.
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
- Si la respuesta es **incorrecta**, la correcta NO se muestra: aparece el botón
  "Revelar respuesta" (estado `quiz.answer_revealed`). Al pulsarlo se pinta la
  opción correcta en verde y aparece "Siguiente". Si acierta, verde inmediato y
  sin botón de revelar. El tiempo ya está congelado tras responder.
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
  "Salir sin guardar" sale sin persistir y BORRA el guardado previo.
  Botón X o ESC cierran el modal.
- SCREEN_START: si existe el guardado, hay botón "Continuar quiz guardado" y
  al pulsar "Comenzar Quiz" se pregunta "¿reanudar sesión anterior?" (Sí →
  reanuda; No → menú de importación).
- Se borra al terminar el quiz (results) y al iniciar uno nuevo.
- Lógica en `quiz_logic.py`: `save_progress`, `load_progress`, `clear_progress`,
  `resume_quiz`. `resume_quiz` respeta el orden guardado (no re-baraja).

## Sistema de actualizaciones (updater.py)

- `check_for_update()` consulta `releases/latest` del repo GitHub y compara
  semver contra `VERSION`. El repo es público: peticiones ANÓNIMAS (sin token
  de `gh`). Devuelve dict o None (siempre actualizado / sin releases), lanza
  `UpdateError` si no hay red.
- Modo fuente: `apply_update()` descarga el zip del tag y copia sobre el
  proyecto PRESERVANDO: `config.json`, `csv/`, `progress.json`,
  `questions.csv/json`, `quiz.log`, `__pycache__`, `.git`.
- Modo instalado (.exe, onedir): `apply_update()` baja el asset `update.zip`
  (carpeta de la app), escribe `apply_update.bat` y lo lanza: cierra la app,
  pisa los archivos de la instalación y la reabre. Así se actualiza EN SITIO:
  no se acumulan .exe nuevos.

## Release / build (instalador + update.zip)

`.github/workflows/build-exe.yml` compila en `windows-latest` (py3.12) cuando
se pushea un tag `v*`, inyecta la versión en `updater.py` y produce:
- `QuizEducativo-setup-vX.Y.Z.exe` — instalador Inno Setup (`installer.iss`,
  a `%LOCALAPPDATA%\QuizEducativo`, sin admin, por eso puede auto-actualizarse).
- `update.zip` — paquete onedir para la auto-actualización en sitio.

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