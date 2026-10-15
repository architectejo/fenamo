from django.db import models


class CleSite(models.Model):
    """Clé d'accès du site public à l'API `/api/v1/site/`. Seule l'empreinte SHA-256 de la clé entière est conservée : la clé n'est
    montrée qu'une fois, à sa création. Le préfixe (8 caractères) sert à retrouver la ligne sans exposer la clé."""

    nom = models.CharField(max_length=100)
    prefixe = models.CharField(max_length=8, unique=True)
    empreinte = models.CharField(max_length=64)
    active = models.BooleanField(default=True)
    cree_le = models.DateTimeField(auto_now_add=True)
    revoquee_le = models.DateTimeField(null=True, blank=True)
    derniere_utilisation = models.DateTimeField(null=True, blank=True)  # écrite au plus une fois par heure

    class Meta:
        verbose_name = 'clé du site'
        verbose_name_plural = 'clés du site'
        ordering = ['-cree_le']

    def __str__(self):
        return f'{self.nom} (fsk_{self.prefixe}_…)'
