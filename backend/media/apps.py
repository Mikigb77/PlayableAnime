from django.apps import AppConfig


class MediaConfig(AppConfig):
    name = "media"
    verbose_name = "Pictures"

    def ready(self) -> None:
        from media import signals

        signals.connect()
