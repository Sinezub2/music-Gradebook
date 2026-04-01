from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import wave
from pathlib import Path
from threading import Lock

from django.conf import settings


class SpeechToTextConfigError(RuntimeError):
    pass


_ASCII_CACHE_COPYING_MARKER = ".music-gradebook-copying"
_ASCII_CACHE_READY_MARKER = ".music-gradebook-ready"
_ASCII_CACHE_LOCK = Lock()
_MODEL_LOAD_LOCK = Lock()
_CACHED_VOSK_MODEL = None


def _is_vosk_model_dir(path: Path) -> bool:
    return (
        path.exists()
        and path.is_dir()
        and (path / "am" / "final.mdl").exists()
        and (path / "conf" / "model.conf").exists()
        and (path / "graph" / "words.txt").exists()
    )


def _candidate_sort_key(path: Path, preferred_name: str) -> tuple[bool, str]:
    return (path.name != preferred_name, path.name)


def _discover_model_path() -> Path:
    configured_path = Path(settings.VOSK_MODEL_PATH)
    if _is_vosk_model_dir(configured_path):
        return configured_path

    search_roots = [configured_path]
    if configured_path.parent != configured_path:
        search_roots.append(configured_path.parent)
    base_models_dir = Path(settings.BASE_DIR) / "models" / "vosk"
    search_roots.append(base_models_dir)

    checked = set()
    for root in search_roots:
        root = root.resolve(strict=False)
        if root in checked or not root.exists():
            continue
        checked.add(root)

        if _is_vosk_model_dir(root):
            return root

        candidates = sorted(root.iterdir(), key=lambda candidate: _candidate_sort_key(candidate, configured_path.name))
        for candidate in candidates:
            if _is_vosk_model_dir(candidate):
                return candidate

    raise SpeechToTextConfigError(
        f"Vosk-модель не найдена или неполная: {configured_path}. "
        "Ожидаются файлы вроде am/final.mdl, conf/model.conf и graph/words.txt."
    )


def _is_ascii_cache_ready(cache_path: Path) -> bool:
    if not _is_vosk_model_dir(cache_path):
        return False
    return not (cache_path / _ASCII_CACHE_COPYING_MARKER).exists()


def _link_or_copy_file(source_file: Path, destination_file: Path) -> None:
    try:
        os.link(source_file, destination_file)
    except OSError:
        shutil.copy2(source_file, destination_file)


def _populate_ascii_cache(source_path: Path, cache_path: Path) -> None:
    if cache_path.exists():
        shutil.rmtree(cache_path, ignore_errors=True)

    cache_path.mkdir(parents=True, exist_ok=True)
    (cache_path / _ASCII_CACHE_COPYING_MARKER).write_text("", encoding="utf-8")

    try:
        for source_root, _, file_names in os.walk(source_path):
            source_root_path = Path(source_root)
            relative_root = source_root_path.relative_to(source_path)
            target_root = cache_path / relative_root
            target_root.mkdir(parents=True, exist_ok=True)

            for file_name in file_names:
                source_file = source_root_path / file_name
                destination_file = target_root / file_name
                _link_or_copy_file(source_file, destination_file)

        (cache_path / _ASCII_CACHE_READY_MARKER).write_text(source_path.as_posix(), encoding="utf-8")
    except Exception:
        shutil.rmtree(cache_path, ignore_errors=True)
        raise
    else:
        copying_marker = cache_path / _ASCII_CACHE_COPYING_MARKER
        if copying_marker.exists():
            copying_marker.unlink()


def _copy_model_to_ascii_cache(source_path: Path) -> Path:
    cache_root = Path(tempfile.gettempdir()) / "music-gradebook-vosk"
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_path = cache_root / source_path.name

    with _ASCII_CACHE_LOCK:
        if not _is_ascii_cache_ready(cache_path):
            _populate_ascii_cache(source_path, cache_path)

    return cache_path


def _build_vosk_model(load_path: Path):
    try:
        from vosk import Model
    except ImportError as exc:
        raise SpeechToTextConfigError("Зависимость vosk не установлена.") from exc

    try:
        return Model(str(load_path))
    except Exception as exc:
        raise SpeechToTextConfigError(
            f"Не удалось загрузить Vosk-модель из {load_path}. Проверьте содержимое папки модели."
        ) from exc


def _resolve_model_load_path() -> Path:
    model_path = _discover_model_path()
    if not str(model_path).isascii():
        return _copy_model_to_ascii_cache(model_path)
    return model_path


def _get_vosk_model():
    global _CACHED_VOSK_MODEL

    if _CACHED_VOSK_MODEL is not None:
        return _CACHED_VOSK_MODEL

    with _MODEL_LOAD_LOCK:
        if _CACHED_VOSK_MODEL is None:
            _CACHED_VOSK_MODEL = _build_vosk_model(_resolve_model_load_path())

    return _CACHED_VOSK_MODEL


def transcribe_wav_bytes(audio_bytes: bytes) -> str:
    try:
        from vosk import KaldiRecognizer
    except ImportError as exc:
        raise SpeechToTextConfigError("Зависимость vosk не установлена.") from exc

    with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
        if wav_file.getnchannels() != 1:
            raise ValueError("Аудио должно быть моно.")
        if wav_file.getsampwidth() != 2:
            raise ValueError("Ожидается 16-bit WAV.")

        recognizer = KaldiRecognizer(_get_vosk_model(), wav_file.getframerate())
        fragments = []
        while True:
            chunk = wav_file.readframes(4000)
            if not chunk:
                break
            if recognizer.AcceptWaveform(chunk):
                partial = json.loads(recognizer.Result()).get("text", "").strip()
                if partial:
                    fragments.append(partial)

        final_text = json.loads(recognizer.FinalResult()).get("text", "").strip()
        if final_text:
            fragments.append(final_text)

    return " ".join(fragment for fragment in fragments if fragment).strip()
