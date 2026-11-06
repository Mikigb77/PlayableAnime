from django.apps import AppConfig


class SpeechConfig(AppConfig):
    name = "speech"
    verbose_name = "Speech"

    def ready(self) -> None:
        from speech import signals

        signals.connect()
