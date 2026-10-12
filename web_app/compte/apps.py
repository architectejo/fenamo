from django.apps import AppConfig


class CompteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'compte'

    def ready(self):
        from compte import signals  # noqa: F401  (enregistre les récepteurs du journal)
