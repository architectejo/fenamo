from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from compte import roles

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
        ANNULATION_DEMANDE_SUPPRESSION = 'annulation_demande_suppression', _('Annulation de demande de suppression')
        SUPPRESSION = 'suppression', _('Suppression logique')
        RESTAURATION = 'restauration', _('Annulation de suppression')
        MODIFICATION = 'modification', _('Modification')
        RATTACHEMENT = 'rattachement', _('Rattachement')
        EXPORT = 'export', _('Export')
        FIN_NOMINATION = 'fin_nomination', _('Fin de nomination')
        CHANGEMENT_ROLE = 'changement_role', _('Changement de rôle ou de périmètre')
        DESACTIVATION_COMPTE = 'desactivation_compte', _('Désactivation de compte')
        REACTIVATION_COMPTE = 'reactivation_compte', _('Réactivation de compte')
        REINITIALISATION_MOT_DE_PASSE = 'reinitialisation_mot_de_passe', _('Réinitialisation de mot de passe')
        ALERTE_MANDAT = 'alerte_mandat', _('Alerte de fin de mandat')
        CONSULTATION_PIECE = 'consultation_piece', _("Consultation d'une pièce")
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


class Nomination(models.Model):
    """Rôle d'un compte dans un périmètre, pour une durée (cahier des charges web § 4.2 et F-02).

    Les droits d'un compte viennent de sa nomination ACTIVE à la date du jour (``compte.services.droits``). Un compte n'a
    qu'une nomination active. Une nomination terminée est conservée (``active`` faux, ``terminee_le``, ``motif_fin``) :
    on ne l'efface pas. La cohérence rôle / périmètre est contrôlée par ``compte.services.nominations``.
    """

    compte = models.ForeignKey(Compte, on_delete=models.CASCADE, related_name='nominations')
    membre = models.ForeignKey('coptapp.Membre', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    role = models.CharField(max_length=2, choices=roles.CHOICES)
    coordination = models.ForeignKey('coptapp.Province', on_delete=models.RESTRICT, null=True, blank=True, related_name='+')
    antenne = models.ForeignKey('coptapp.Antenne', on_delete=models.RESTRICT, null=True, blank=True, related_name='+')
    association = models.ForeignKey('coptapp.AssociationMembre', on_delete=models.RESTRICT, null=True, blank=True, related_name='+')
    debut = models.DateField(default=timezone.localdate)
    fin = models.DateField(null=True, blank=True)
    duree_mandat_ans = models.PositiveSmallIntegerField(null=True, blank=True)
    nomme_par = models.ForeignKey(Compte, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    active = models.BooleanField(default=True)
    terminee_le = models.DateTimeField(null=True, blank=True)
    terminee_par = models.ForeignKey(Compte, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    motif_fin = models.TextField(blank=True)
    alerte_envoyee_le = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = _('nomination')
        verbose_name_plural = _('nominations')
        ordering = ['-debut', '-id']
        indexes = [
            models.Index(fields=['compte', 'active'], name='nomination_compte_active_idx'),
            models.Index(fields=['role'], name='nomination_role_idx'),
            models.Index(fields=['fin'], name='nomination_fin_idx'),
        ]
        constraints = [
            # Une seule nomination active par compte (appliqué par la base sous SQLite ; sous MySQL par le service).
            models.UniqueConstraint(fields=['compte'], condition=Q(active=True), name='une_nomination_active_par_compte'),
        ]

    def __str__(self):
        return f'{self.compte} : {self.role}'

    def est_echue(self, aujourdhui=None):
        """Vrai si la date de fin du mandat est dépassée. Une nomination ÉCHUE reste valable pour les droits tant qu'elle n'est pas
        terminée à la main (décision FENAMO : alerte seulement, jamais de coupure automatique)."""
        return self.fin is not None and self.fin < (aujourdhui or timezone.localdate())

    def clean(self):
        from compte.services.nominations import valider_coherence
        super().clean()
        valider_coherence(self.role, self.coordination_id, self.antenne_id, self.association_id)
