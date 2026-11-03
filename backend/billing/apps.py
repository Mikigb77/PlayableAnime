from django.apps import AppConfig


class BillingConfig(AppConfig):
    name = "billing"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from billing import signals  # noqa: F401  (connects the receivers)
