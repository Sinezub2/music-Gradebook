import shutil
import threading
import time
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from django.test import SimpleTestCase

from . import speech


class SpeechModuleTests(SimpleTestCase):
    def setUp(self):
        temp_root_base = Path(__file__).resolve().parents[2] / "tmp_test_speech"
        temp_root_base.mkdir(exist_ok=True)
        self.temp_root = temp_root_base / f"case_{uuid4().hex}"
        self.temp_root.mkdir()
        self.addCleanup(lambda: shutil.rmtree(self.temp_root, ignore_errors=True))
        self.addCleanup(self._reset_model_cache)
        self._reset_model_cache()

    def _reset_model_cache(self):
        speech._CACHED_VOSK_MODEL = None

    def _create_model_dir(self, root: Path, name: str) -> Path:
        model_dir = root / name
        (model_dir / "am").mkdir(parents=True, exist_ok=True)
        (model_dir / "conf").mkdir(parents=True, exist_ok=True)
        (model_dir / "graph").mkdir(parents=True, exist_ok=True)
        (model_dir / "am" / "final.mdl").write_text("", encoding="utf-8")
        (model_dir / "conf" / "model.conf").write_text("", encoding="utf-8")
        (model_dir / "graph" / "words.txt").write_text("", encoding="utf-8")
        return model_dir

    def _create_small_model_dir(self, root: Path, name: str) -> Path:
        model_dir = root / name
        (model_dir / "am").mkdir(parents=True, exist_ok=True)
        (model_dir / "conf").mkdir(parents=True, exist_ok=True)
        (model_dir / "graph" / "phones").mkdir(parents=True, exist_ok=True)
        (model_dir / "am" / "final.mdl").write_text("", encoding="utf-8")
        (model_dir / "conf" / "model.conf").write_text("", encoding="utf-8")
        (model_dir / "graph" / "HCLr.fst").write_text("", encoding="utf-8")
        (model_dir / "graph" / "phones" / "word_boundary.int").write_text("", encoding="utf-8")
        return model_dir

    def test_discover_model_path_prefers_configured_model_name_inside_parent_directory(self):
        models_root = self.temp_root / "models" / "vosk"
        self._create_model_dir(models_root, "vosk-model-ru-0.22")
        expected_model = self._create_model_dir(models_root, "vosk-model-small-ru-0.22")

        with self.settings(
            BASE_DIR=self.temp_root,
            VOSK_MODEL_PATH=models_root / "vosk-model-small-ru-0.22",
        ):
            discovered_model = speech._discover_model_path()

        self.assertEqual(discovered_model, expected_model)

    def test_discover_model_path_accepts_project_models_root_as_full_model_directory(self):
        models_root = self._create_model_dir(self.temp_root / "models", "vosk")
        self._create_small_model_dir(models_root, "vosk-model-small-ru-0.22")

        with self.settings(
            BASE_DIR=self.temp_root,
            VOSK_MODEL_PATH=models_root,
        ):
            discovered_model = speech._discover_model_path()

        self.assertEqual(discovered_model, models_root)

    def test_get_vosk_model_builds_only_once_for_concurrent_calls(self):
        resolved_model_path = self._create_model_dir(self.temp_root, "vosk-model-small-ru-0.22")
        barrier = threading.Barrier(5)
        results = [None] * 4
        build_calls = []

        def fake_build(load_path: Path):
            build_calls.append(load_path)
            time.sleep(0.1)
            return {"path": str(load_path)}

        def load_model(index: int):
            barrier.wait()
            results[index] = speech._get_vosk_model()

        with patch.object(speech, "_resolve_model_load_path", return_value=resolved_model_path):
            with patch.object(speech, "_build_vosk_model", side_effect=fake_build):
                threads = [threading.Thread(target=load_model, args=(index,)) for index in range(4)]
                for thread in threads:
                    thread.start()

                barrier.wait()

                for thread in threads:
                    thread.join()

        self.assertEqual(len(build_calls), 1)
        self.assertTrue(all(result == results[0] for result in results))

    def test_discover_model_path_accepts_small_model_layout_without_words_txt(self):
        models_root = self.temp_root / "models" / "vosk"
        expected_model = self._create_small_model_dir(models_root, "vosk-model-small-ru-0.22")

        with self.settings(
            BASE_DIR=self.temp_root,
            VOSK_MODEL_PATH=models_root / "vosk-model-small-ru-0.22",
        ):
            discovered_model = speech._discover_model_path()

        self.assertEqual(discovered_model, expected_model)
