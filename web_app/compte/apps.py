from django.apps import AppConfig


class CompteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'compte'

    def ready(self):
        from compte import checks, signals  # noqa: F401  (enregistre les contrôles de déploiement et les récepteurs du journal)
