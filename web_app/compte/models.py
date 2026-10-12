from django.contrib.auth.models import AbstractUser
from django.db import models

# Create your models here.
class Compte(AbstractUser, models.Model):
    membreId = models.IntegerField(null=True, blank=True)
    privilege1 = models.BooleanField(default=False, null=True, blank=True)
    privilege2 = models.BooleanField(default=False, null=True, blank=True)
    privilege3 = models.BooleanField(default=False, null=True, blank=True)
    privilege4 = models.BooleanField(default=False, null=True, blank=True)
    privilege5 = models.BooleanField(default=False, null=True, blank=True)
    privilege = models.IntegerField(null=True, blank=True)
    editor = models.BooleanField(default=False, null=True, blank=True)
    # Vrai après création par un super-utilisateur : changement imposé à la première connexion.
    doit_changer_mot_de_passe = models.BooleanField(default=False)
