from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

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


class JournalAction(models.Model):
    """Journal d'activités (F-70) : une ligne par changement d'état. Jamais de mot de passe, jeton ni pièce
    (voir compte/services/journal.py). Les lignes ne se modifient pas."""

    class Action(models.TextChoices):
        CONNEXION = 'connexion', _('Connexion')
        DECONNEXION = 'deconnexion', _('Déconnexion')
        ECHEC_CONNEXION = 'echec_connexion', _('Échec de connexion')
        VERROUILLAGE_CONNEXION = 'verrouillage_connexion', _('Blocage après échecs de connexion')
        CREATION_COMPTE = 'creation_compte', _('Création de compte')
        NOMINATION = 'nomination', _('Nomination')
        ATTRIBUTION_PRIVILEGES = 'attribution_privileges', _('Attribution de privilèges')
        CHANGEMENT_MOT_DE_PASSE = 'changement_mot_de_passe', _('Changement de mot de passe')
        VALIDATION = 'validation', _('Validation')
        RENVOI = 'renvoi', _('Renvoi au niveau inférieur')
        DEMANDE_SUPPRESSION = 'demande_suppression', _('Demande de suppression')
        SUPPRESSION = 'suppression', _('Suppression logique')
        RESTAURATION = 'restauration', _('Annulation de suppression')
        MODIFICATION = 'modification', _('Modification')
        RATTACHEMENT = 'rattachement', _('Rattachement')
        EXPORT = 'export', _('Export')
        VERROUILLAGE_APPLICATION = 'verrouillage_application', _("Verrouillage de l'application")
        PAIEMENT = 'paiement', _('Paiement')

    auteur = models.ForeignKey(Compte, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    role = models.CharField(max_length=60, blank=True)
    date = models.DateTimeField(default=timezone.now)
    action = models.CharField(max_length=40, choices=Action.choices)
    objet_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    objet_id = models.PositiveBigIntegerField(null=True, blank=True)
    objet_libelle = models.CharField(max_length=255, blank=True)
    avant = models.JSONField(null=True, blank=True)
    apres = models.JSONField(null=True, blank=True)
    motif = models.TextField(blank=True)
    coordination = models.ForeignKey('coptapp.Province', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    antenne = models.ForeignKey('coptapp.Antenne', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = _("ligne du journal d'activités")
        verbose_name_plural = _("journal d'activités")
        indexes = [
            models.Index(fields=['date'], name='journal_date_idx'),
            models.Index(fields=['action'], name='journal_action_idx'),
            models.Index(fields=['auteur', 'date'], name='journal_auteur_date_idx'),
            models.Index(fields=['objet_type', 'objet_id'], name='journal_objet_idx'),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Une ligne du journal d'activités ne se modifie pas.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.date:%Y-%m-%d %H:%M} {self.action} {self.objet_libelle}'
