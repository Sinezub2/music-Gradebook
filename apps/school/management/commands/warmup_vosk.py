from django.core.management.base import BaseCommand, CommandError

from apps.school.speech import SpeechToTextConfigError, warmup_vosk_model


class Command(BaseCommand):
    help = "Loads the configured Vosk model before the app starts serving speech requests."

    def handle(self, *args, **options):
        self.stdout.write("Warming up Vosk model...")
        try:
            model_path = warmup_vosk_model()
        except SpeechToTextConfigError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Vosk model is ready: {model_path}"))
