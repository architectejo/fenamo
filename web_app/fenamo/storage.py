"""Stockage PRIVÉ des pièces et des photos des membres (cahier des charges web § 9.4).

Les fichiers sont écrits sous ``PRIVATE_MEDIA_ROOT``, HORS de la racine web : aucun serveur ne les sert directement
sous ``/media/``. Ils ne sortent que par la vue contrôlée ``coptapp.views.fichiers`` (connexion, droit, périmètre).

``url()`` renvoie l'adresse de cette vue (par nom de fichier) : un gabarit qui lit encore ``champ.url`` obtient donc un
lien protégé, jamais un lien public. Les gabarits neufs utilisent la balise ``{% url_fichier objet "champ" %}``.
"""
from urllib.parse import quote

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.urls import reverse


class StockagePrive(FileSystemStorage):
    """Système de fichiers privé ; le dossier est lu dans les réglages à chaque usage (testable, jamais figé)."""

    @property
    def base_location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self):
        import os
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None

    def url(self, name):
        return reverse('fichier-nom', kwargs={'nom': quote(str(name).lstrip('./'))})  # vue contrôlée, jamais /media/


def stockage_prive():
    """Fabrique référencée par les champs (``storage=stockage_prive``) : stable pour les migrations."""
    return StockagePrive()
