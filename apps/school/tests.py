import shutil
import threading
import time
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import Profile

from . import speech
from .models import Course, CourseType, Enrollment


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


class SpeechViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="speech-user", password="test-pass-123")
        Profile.objects.create(user=self.user, role=Profile.Role.TEACHER)
        self.client.force_login(self.user)

    def test_speech_warmup_returns_ready_json(self):
        with patch("apps.school.views.warmup_vosk_model", return_value=Path("/tmp/vosk")) as warmup:
            response = self.client.get(reverse("speech_warmup"))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode("utf-8"),
            {"status": "ready", "model_path": str(Path("/tmp/vosk"))},
        )
        warmup.assert_called_once_with()

    def test_speech_transcribe_returns_json_for_unexpected_errors(self):
        audio = SimpleUploadedFile("speech.wav", b"RIFF", content_type="audio/wav")

        with patch("apps.school.views.transcribe_wav_bytes", side_effect=RuntimeError("boom")):
            response = self.client.post(reverse("speech_transcribe"), {"audio": audio})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertJSONEqual(
            response.content.decode("utf-8"),
            {"error": "Внутренняя ошибка распознавания речи."},
        )


class TeacherStudentWorkspaceTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.course_type = CourseType.objects.create(name="Фортепиано")
        self.teacher = self._create_user("teacher_workspace", Profile.Role.TEACHER)
        self.student = self._create_user("student_workspace", Profile.Role.STUDENT, cycle=Profile.Cycle.GENERAL)
        self.course = Course.objects.create(name="Фортепиано 1", course_type=self.course_type, teacher=self.teacher)
        Enrollment.objects.create(course=self.course, student=self.student)

    def _create_user(self, username: str, role: str, cycle: str = Profile.Cycle.GENERAL):
        user = self.user_model.objects.create_user(
            username=username,
            password="pass12345",
            first_name=username,
            last_name="User",
        )
        Profile.objects.create(user=user, role=role, cycle=cycle)
        return user

    def test_teacher_can_change_student_cycle_from_workspace(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse("teacher_student_workspace", args=[self.student.id]),
            data={"cycle": Profile.Cycle.ACCELERATED},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.cycle, Profile.Cycle.ACCELERATED)

    def test_workspace_does_not_show_redundant_goal_create_button(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("teacher_student_workspace", args=[self.student.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Полугодовой план")
        self.assertNotContains(response, "Добавить в полугодовой план")
