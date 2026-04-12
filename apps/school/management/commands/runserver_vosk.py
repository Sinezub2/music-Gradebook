import logging

from django.core.management.commands.runserver import Command as RunserverCommand

from apps.school.speech import SpeechToTextConfigError, warmup_vosk_model

logger = logging.getLogger(__name__)


class Command(RunserverCommand):
    help = "Runs the Django server after warming up the configured Vosk model."

    def inner_run(self, *args, **options):
        self.stdout.write("Warming up Vosk model...")
        try:
            model_path = warmup_vosk_model()
        except SpeechToTextConfigError as exc:
            self.stderr.write(self.style.WARNING(f"Vosk warm-up failed: {exc}"))
        except Exception:
            logger.exception("Unexpected Vosk warm-up failure during server startup.")
            self.stderr.write(self.style.WARNING("Unexpected Vosk warm-up failure. Check the app logs."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Vosk model is ready: {model_path}"))

        return super().inner_run(*args, **options)
