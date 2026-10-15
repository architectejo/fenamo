from django.db import models


class Telechargement(models.Model):
    """Compteur de téléchargements (S-10), tenu par le site lui-même : aucune donnée personnelle, un total par fichier."""

    cle = models.CharField(max_length=200, unique=True)  # « document:charte », « application:fenamo-1-0-0 »
    total = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.cle} : {self.total}"
