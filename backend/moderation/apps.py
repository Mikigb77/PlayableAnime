from django.apps import AppConfig


class ModerationConfig(AppConfig):
    name = "moderation"
    verbose_name = "Reports"

    def ready(self) -> None:
        from moderation import signals

        signals.connect(self)
