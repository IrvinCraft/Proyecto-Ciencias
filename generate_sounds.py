"""
Genera los archivos .wav de sonido para el quiz.
Usa solo la biblioteca estándar de Python (wave, math, struct).
Ejecutar una vez:  python generate_sounds.py
"""
import wave
import math
import struct
import os

SOUNDS_DIR = os.path.join(os.path.dirname(__file__), "assets", "sounds")
SAMPLE_RATE = 44100


def _tone(frequency, duration, amplitude=0.5, fade=0.01):
    """Genera una onda senoidal con atenuación de entrada/salida (fade in/out)."""
    samples = []
    n = int(SAMPLE_RATE * duration)
    fade_samples = int(SAMPLE_RATE * fade)
    for i in range(n):
        t = i / SAMPLE_RATE
        value = math.sin(2 * math.pi * frequency * t)
        # Fade in
        if i < fade_samples:
            value *= i / max(fade_samples, 1)
        # Fade out
        if i > n - fade_samples:
            value *= (n - i) / max(fade_samples, 1)
        samples.append(int(value * amplitude * 32767))
    return samples


def _save_wav(filename, samples):
    """Guarda una lista de samples PCM en un archivo .wav mono 16-bit."""
    path = os.path.join(SOUNDS_DIR, filename)
    os.makedirs(SOUNDS_DIR, exist_ok=True)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(struct.pack("<" + ("h" * len(samples)), *samples))
    print(f"  ✓ {filename} ({len(samples)/SAMPLE_RATE:.2f}s)")


def _silence(duration):
    """Genera silencio."""
    return [0] * int(SAMPLE_RATE * duration)


def _sequence(frequencies, note_duration=0.25, amplitude=0.4):
    """Genera una secuencia de notas (melodía ascendente)."""
    samples = []
    for freq in frequencies:
        samples.extend(_tone(freq, note_duration, amplitude, fade=0.02))
        samples.extend(_silence(0.03))  # breve pausa entre notas
    return samples


def generate_all():
    """Genera todos los efectos de sonido necesarios."""
    os.makedirs(SOUNDS_DIR, exist_ok=True)
    print("Generando efectos de sonido...")

    # 1. Sonido de clic/inicio — pitido corto agudo
    _save_wav("click.wav", _tone(880, 0.1, 0.4, fade=0.02))

    # 2. Sonido de inicio — melodía ascendente amable
    _save_wav("start.wav", _sequence([523, 659, 784, 1047], 0.15, 0.5))

    # 3. Sonido de error — tono descendente grave (buzo)
    _save_wav("error.wav", _tone(300, 0.7, 0.5, fade=0.1))

    # 4. Sonido de acierto — tono ascendente agudo (cascabel)
    _save_wav("correct.wav", _sequence([523, 659, 784], 0.15, 0.5))

    # 5. Sonido de celebración — escala ascendente completa
    _save_wav("celebration.wav", _sequence([523, 587, 659, 740, 831, 988], 0.12, 0.5))

    print("¡Todos los sonidos generados en assets/sounds/")


if __name__ == "__main__":
    generate_all()
