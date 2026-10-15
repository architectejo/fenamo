from django.apps import AppConfig


class VirtrineConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'virtrine'

    def ready(self):
        """Valide et renomme les fichiers publics (PDF des documents, APK de l'application) avant l'enregistrement."""
        from django.db.models.signals import pre_save

        from virtrine.models import Config, DocumentPublic
        from virtrine.services.medias import traiter_fichiers_publics
        for modele in (DocumentPublic, Config):
            pre_save.connect(traiter_fichiers_publics, sender=modele, dispatch_uid=f'fichiers-publics-{modele._meta.label_lower}')
