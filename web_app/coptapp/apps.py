from django.apps import AppConfig


class CoptappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'coptapp'

    def ready(self):
        """Traite toute image téléversée (type réel, nom aléatoire, taille, vignette) avant l'enregistrement."""
        from django.apps import apps
        from django.db import models
        from django.db.models.signals import pre_save

        from coptapp.validators import traiter_images_avant_enregistrement, traiter_pieces_avant_enregistrement
        for modele in apps.get_models():
            if modele._meta.app_label in ('coptapp', 'virtrine') and any(
                isinstance(champ, models.ImageField) for champ in modele._meta.concrete_fields
            ):
                pre_save.connect(traiter_images_avant_enregistrement, sender=modele,
                                 dispatch_uid=f'images-{modele._meta.label_lower}')
            if modele._meta.app_label in ('coptapp', 'virtrine') and any(
                isinstance(champ, models.FileField) and not isinstance(champ, models.ImageField)
                for champ in modele._meta.concrete_fields
            ):
                pre_save.connect(traiter_pieces_avant_enregistrement, sender=modele,
                                 dispatch_uid=f'pieces-{modele._meta.label_lower}')
