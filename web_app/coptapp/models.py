from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from compte.models import Compte
from coptapp.validators import valider_image, valider_piece
from fenamo.storage import stockage_prive
from datetime import date
import logging

# Create your models here.

#Configurations
class Province(models.Model):
    """Coordination provinciale (charte, annexe C). ``code`` est le code officiel, unique, qui sert à numéroter les engins ;
    ``sigle`` est l'ancien sigle (repli tant que le code n'est pas renseigné)."""

    class Meta:
        verbose_name = _('coordination provinciale')
        verbose_name_plural = _('coordinations provinciales')
        ordering = ['ordre', 'nom']

    user = models.ForeignKey(Compte, on_delete=models.RESTRICT, null=True, blank=True)
    nom = models.CharField(max_length=50, null=True, blank=True)
    sigle = models.CharField(max_length=5, null=True, blank=True)
    code = models.CharField(max_length=5, unique=True, null=True, blank=True, verbose_name=_('code officiel'))
    ordre = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name=_("ordre d'affichage"))
    mise_a_jour = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return f"{self.nom}"

    @staticmethod
    def normaliser_code(code):
        """Code en majuscules sans espaces ; None si vide (l'unicité ne porte que sur les codes réels)."""
        return (code or '').strip().upper() or None

    def code_fige(self):
        """Vrai si le code enregistré ne peut plus changer : un engin a été numéroté AVEC ce code (son numéro se termine par
        le code, précédé de chiffres). Une coordination sans code enregistré n'est jamais figée, même si elle a d'anciens
        engins numérotés avec son sigle : on peut encore lui donner son code."""
        if not self.pk:
            return False
        ancien = Province.objects.filter(pk=self.pk).values_list('code', flat=True).first()
        if not ancien:
            return False
        numeros = Moto.objects.filter(province=self, numero__endswith=ancien).values_list('numero', flat=True)
        return any(numero[:-len(ancien)].isdigit() for numero in numeros)

    def _verifier_code_modifiable(self):
        if self.pk and self.code_fige():
            ancien = Province.objects.filter(pk=self.pk).values_list('code', flat=True).first()
            if ancien != self.normaliser_code(self.code):
                raise ValidationError({'code': _("Le code ne peut plus changer : des engins sont déjà numérotés avec ce code.")})

    def clean(self):
        super().clean()
        self._verifier_code_modifiable()

    def save(self, *args, **kwargs):
        self._verifier_code_modifiable()  # la règle vaut aussi hors formulaire (shell, services)
        self.code = self.normaliser_code(self.code)  # normalisation faite ICI, une seule fois
        super().save(*args, **kwargs)


class Ville(models.Model):
    user = models.ForeignKey(Compte, on_delete=models.RESTRICT, null=True, blank=True)
    province = models.ForeignKey(Province, on_delete=models.RESTRICT, null=True, blank=True)
    nom = models.CharField(max_length=50, null=True, blank=True)
    mise_a_jour = models.DateTimeField(auto_now=True, null=True, blank=True)
    
    def __str__(self):
        return f"{self.nom}"
    
class AssociationMembre(models.Model):
    class Meta:
        verbose_name = _('association membre')
        verbose_name_plural = _('associations membres')

    users = models.ManyToManyField(Compte, blank=True, related_name="users_of_structure")
    ville = models.ForeignKey(Ville, on_delete=models.SET_NULL, null=True, blank=True)
    province = models.ForeignKey(Province, on_delete=models.SET_NULL, null=True, blank=True)
    antenne = models.ForeignKey('Antenne', on_delete=models.SET_NULL, null=True, blank=True, related_name='associations')
    type_de_structure = models.CharField(max_length=50, null=True,blank=True, verbose_name=_("type d'association"))
    num_justice = models.CharField(max_length=50, null=True, blank=True, unique=True)
    capture_justice = models.ImageField(upload_to='./F92/', null=True, blank=True, validators=[valider_image], storage=stockage_prive)
    nom = models.CharField(max_length=255, null=True, blank=True)
    nom_responsable = models.CharField(max_length=255, null=True, blank=True)
    sigle = models.CharField(max_length=50, null=True, blank=True)
    logo = models.ImageField(upload_to='./logo/', null=True, blank=True, validators=[valider_image])
    adresse = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=25, default='+243...', null=True, blank=True)
    email = models.EmailField(max_length=100, default='@', null=True, blank=True)
    preuve_de_paiement = models.ImageField(upload_to='./frais/', null=True, blank=True, validators=[valider_image], storage=stockage_prive)
    twitter = models.CharField(max_length=500, null=True, blank=True)
    facebook = models.CharField(max_length=500, null=True, blank=True)
    instagram = models.CharField(max_length=500, null=True, blank=True)
    linkedin = models.CharField(max_length=500, null=True, blank=True)

    def __str__(self):
        return f"{self.sigle}"

class Antenne(models.Model):
    """Antenne (commune ou territoire, charte art. 66) d'une coordination provinciale. ``ville_origine`` garde le lien avec la
    « ville » héritée dont l'antenne est issue ; ``structure`` est l'ancien rattachement à une association membre."""

    class Type(models.TextChoices):
        COMMUNE = 'commune', _('commune')
        TERRITOIRE = 'territoire', _('territoire')

    user = models.ForeignKey(Compte, on_delete=models.RESTRICT, null=True, blank=True)
    structure = models.ForeignKey(AssociationMembre, on_delete=models.RESTRICT, null=True, blank=True,
                                  verbose_name=_('association membre'), related_name='antennes_heritees')
    coordination = models.ForeignKey(Province, on_delete=models.RESTRICT, null=True, blank=True, related_name='antennes')
    type = models.CharField(max_length=10, choices=Type.choices, blank=True)
    ville_origine = models.OneToOneField(Ville, on_delete=models.SET_NULL, null=True, blank=True, related_name='antenne_issue')
    nom = models.CharField(max_length=50, null=True, blank=True)
    zone = models.CharField(max_length=50, null=True, blank=True)
    code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    mise_a_jour = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return f"{self.nom}"

    def save(self, *args, **kwargs):
        if self.code is not None:
            self.code = self.code.strip() or None  # jamais de chaîne vide : l'unicité ne porte que sur les codes réels
        super().save(*args, **kwargs)


# ---------------------------------------------------------------- état unique du membre (cahier des charges § 4.4)

logger = logging.getLogger(__name__)

# SEULE définition du circuit de validation (droits.py, droits_herites.py et transitions.py l'importent d'ici).
CIRCUIT = ('saisi', 'valide_antenne', 'valide_province', 'actif')

ETATS_MEMBRE = ('saisi', 'valide_antenne', 'valide_province', 'actif', 'renvoye', 'a_renouveler', 'supprime')
ETATS_MEMBRE_CHOICES = [
    ('saisi', _('Saisi')), ('valide_antenne', _('Validé antenne')), ('valide_province', _('Validé province')), ('actif', _('Actif')),
    ('renvoye', _('Renvoyé')), ('a_renouveler', _('À renouveler')), ('supprime', _('Supprimé')),
]
CHAMPS_MIROIRS = ('is_delete', 'is_validate2', 'is_validate3', 'renvoye')
# Colonnes d'état : jamais réécrites par un save() sans update_fields (mise à jour perdue), sauf demande explicite (voir Membre.save).
CHAMPS_ETAT = ('etat', 'etat_precedent', 'motif_renvoi', *CHAMPS_MIROIRS)


def miroirs_de(etat, etat_precedent=''):
    """Valeurs des anciens booléens (miroirs lus par ``mobapp`` et les gabarits hérités) déduites de l'état UNIQUE.

    Un membre supprimé garde les drapeaux de validation de son état d'avant la suppression."""
    effectif = etat_precedent if etat == 'supprime' and etat_precedent in ETATS_MEMBRE else etat
    return {
        'is_delete': etat == 'supprime',
        'is_validate2': effectif in ('valide_antenne', 'valide_province', 'actif', 'a_renouveler'),
        'is_validate3': effectif in ('actif', 'a_renouveler'),
        'renvoye': etat == 'renvoye',
    }


def etat_depuis_drapeaux(is_delete=False, is_validate2=False, is_validate3=False, renvoye=False):
    """Règle TRANSITOIRE : état déduit des anciens booléens (écritures héritées, données non migrées)."""
    if is_delete:
        return 'supprime'
    if renvoye:
        return 'renvoye'
    if is_validate3:
        return 'actif'
    if is_validate2:
        return 'valide_antenne'
    return 'saisi'


class MembreQuerySet(models.QuerySet):
    """``update()`` garde l'état unique et ses miroirs cohérents : une écriture de ``etat`` met les miroirs à jour et vide
    ``etat_precedent`` (sauf pour « supprime »), comme ``save()`` ; une écriture HÉRITÉE des booléens (``update(is_validate2=True)``)
    est traduite en état et AVERTIT dans le journal technique. TRANSITOIRE : voir docs/correspondance-etat-membre.md (plan de retrait)."""

    def update(self, **champs):
        heritage = [c for c in CHAMPS_MIROIRS if c in champs]
        if 'etat' in champs:
            if champs['etat'] != 'supprime':
                champs.setdefault('etat_precedent', '')
            precedent = champs.get('etat_precedent', '')
            champs = {**{k: v for k, v in miroirs_de(champs['etat'], precedent).items() if k not in champs}, **champs}
            return super().update(**champs)
        if not heritage:
            return super().update(**champs)
        logger.warning("Membre.objects.update(%s) : écriture héritée des booléens traduite en état (règle transitoire).", ', '.join(heritage))
        total = 0
        lignes = list(self.values('pk', 'etat', 'etat_precedent', *CHAMPS_MIROIRS))
        groupes = {}
        for ligne in lignes:
            nouveau = {c: champs.get(c, ligne[c]) for c in CHAMPS_MIROIRS}
            etat = etat_depuis_drapeaux(**nouveau)
            if nouveau == miroirs_de(ligne['etat'], ligne['etat_precedent']):
                etat = ligne['etat']  # aucun changement réel : l'état fin (valide_province…) n'est pas écrasé par la lecture grossière des booléens
            precedent = ligne['etat_precedent']
            if etat == 'supprime' and ligne['etat'] != 'supprime':
                precedent = ligne['etat']  # l'état d'avant la suppression est l'état courant, pas un état recalculé
            elif etat != 'supprime':
                precedent = ''
            groupes.setdefault((etat, precedent), []).append(ligne['pk'])
        autres = {k: v for k, v in champs.items() if k not in CHAMPS_MIROIRS}
        for (etat, precedent), pks in groupes.items():
            total += models.QuerySet(model=self.model, using=self.db).filter(pk__in=pks).update(
                etat=etat, etat_precedent=precedent, **miroirs_de(etat, precedent), **autres)
        return total


#Démande du client
class Membre(models.Model):
    idf = models.CharField(max_length=50, null=True, blank=True)
    # Mot de passe de l'espace mobile /mob/ : TOUJOURS un hachage Django (128 caractères), jamais le texte en clair.
    password = models.CharField(max_length=128, null=True, blank=True)
    fiche_id = models.FileField(upload_to="./fiche_id/", null=True, blank=True, validators=[valider_piece], storage=stockage_prive)
    user = models.ForeignKey(Compte, on_delete=models.SET_NULL, null=True, blank=True)
    antenne = models.ForeignKey(Antenne, on_delete=models.SET_NULL, null=True, blank=True)
    ville = models.ForeignKey(Ville, on_delete=models.SET_NULL, null=True, blank=True)
    province = models.ForeignKey(Province, on_delete=models.SET_NULL, null=True, blank=True)
    structure = models.ForeignKey(to=AssociationMembre, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_('association membre'))
    code_parking = models.CharField(max_length=100, null=True, blank=True)
    nom = models.CharField(max_length=50, null=True, blank=True)
    date_naissance = models.DateField(null=True, blank=True)
    lieux_naissance = models.CharField(max_length=50, null=True, blank=True)
    genre = models.CharField(max_length=20, null=True, blank=True)
    titre = models.CharField(max_length=10, null=True, blank=True)
    fonction = models.CharField(max_length=30, null=True, blank=True)
    comite = models.CharField(max_length=50, null=True, blank=True)
    brevet = models.CharField(max_length=15, null=True, blank=True)
    etat_civil = models.CharField(max_length=50, null=True, blank=True)
    nom_epouse = models.CharField(max_length=50, null=True, blank=True)
    nation = models.CharField(max_length=50, default="Congolaise", null=True, blank=True)
    numero_carte_d_electeur = models.CharField(max_length=20, null=True, blank=True)
    numero_carte_de_membre = models.CharField(max_length=20, null=True, blank=True)
    nom_pere = models.CharField(max_length=50, null=True, blank=True)
    nom_mere = models.CharField(max_length=50, null=True, blank=True)
    village = models.CharField(max_length=30, null=True, blank=True)
    chefferie = models.CharField(max_length=30, null=True, blank=True)
    territoire = models.CharField(max_length=30, null=True, blank=True)
    province_origine = models.CharField(max_length=20, null=True, blank=True)
    photo = models.ImageField(upload_to='./', null=True, blank=True, validators=[valider_image], storage=stockage_prive)
    adresse = models.CharField(max_length=255, null=True, blank=True)
    telephone = models.CharField(max_length=20, null=True, blank=True)
    mail = models.EmailField(max_length=100, null=True, blank=True)
    categorie = models.CharField(max_length=20, null=True, blank=True)
    permis = models.CharField(max_length=20, null=True, blank=True)
    qualite = models.CharField(max_length=100, null=True, blank=True)
    autre_asb = models.CharField(max_length=255, null=True, blank=True)
    a_propos = models.TextField(blank=True, null=True)
    is_user = models.BooleanField(default=False, null=True, blank=True)
    is_delete = models.BooleanField(default=False)
    # Demande de suppression (F-25) : un agent ou un validateur demande, SU / privilege5 exécute (is_delete).
    suppression_demandee = models.BooleanField(default=False)
    motif_suppression = models.TextField(blank=True, default='')
    # Auteur de la demande en cours : lui (ou qui exécute) peut l'annuler.
    suppression_demandee_par = models.ForeignKey(Compte, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    # ÉTAT UNIQUE (§ 4.4) : seule source de vérité du circuit de validation. Les booléens ci-dessous (is_delete, is_validate2,
    # is_validate3, renvoye) en sont des MIROIRS recalculés par save() pour ``mobapp`` et les écrans hérités : ne les écrire nulle part ailleurs.
    etat = models.CharField(max_length=20, choices=ETATS_MEMBRE_CHOICES, default='saisi', db_index=True)
    etat_precedent = models.CharField(max_length=20, blank=True, default='', help_text=_("état d'avant la suppression (restauration)"))
    # Renvoi avec motif (F-23) : motif affiché au niveau juste en dessous ; vidé quand le dossier avance de nouveau.
    renvoye = models.BooleanField(default=False)
    motif_renvoi = models.TextField(blank=True, default='')
    is_validate1 = models.BooleanField(default=True)
    is_validate2 = models.BooleanField(default=False)
    is_validate3 = models.BooleanField(default=False)
    is_membre = models.BooleanField(default=True)
    mise_a_jour = models.DateField(auto_now=True, null=True, blank=True)
    updated = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    objects = MembreQuerySet.as_manager()

    class Meta:
        indexes = [models.Index(fields=['antenne', 'etat'], name='membre_antenne_etat_idx')]

    @classmethod
    def from_db(cls, db, field_names, values):
        membre = super().from_db(db, field_names, values)
        membre._etat_charge = membre.etat if 'etat' in field_names else None
        return membre

    def save(self, *args, **kwargs):
        """Écrit le membre SANS jamais réécrire l'état par inadvertance.

        - ``save()`` sans ``update_fields`` sur un membre existant ne réécrit PAS les colonnes d'état (``etat``, ``etat_precedent``,
          ``motif_renvoi`` et les miroirs) : une instance lue avant une validation ne l'annule plus (mise à jour perdue). L'état ne
          change que par ``coptapp.services.transitions`` (qui passe par ``update_fields``), ou si le code a changé ``etat`` lui-même.
        - Création : l'état vient de ``etat`` ; les miroirs sont recalculés depuis lui.
        - Règle TRANSITOIRE (écritures héritées) : si ``etat`` n'a pas été touché alors que les anciens booléens ont changé, l'état est
          déduit des booléens, en prenant ``self.etat`` comme état précédent d'une suppression, et un avertissement est journalisé."""
        charge = getattr(self, '_etat_charge', 'saisi' if self._state.adding else None)
        etat_modifie = charge is not None and self.etat != charge
        if charge is not None and not etat_modifie and self._miroirs_actuels() != miroirs_de(self.etat, self.etat_precedent):
            nouvel = etat_depuis_drapeaux(self.is_delete, self.is_validate2, self.is_validate3, self.renvoye)
            if nouvel != self.etat:
                logger.warning("Membre %s : écriture héritée des booléens traduite en état %s (règle transitoire).", self.pk, nouvel)
                if nouvel == 'supprime':
                    self.etat_precedent = self.etat
                self.etat = nouvel
                etat_modifie = True
        if self.etat != 'supprime':
            self.etat_precedent = ''
        for champ, valeur in miroirs_de(self.etat, self.etat_precedent).items():
            setattr(self, champ, valeur)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            if set(CHAMPS_ETAT) & set(update_fields):
                kwargs['update_fields'] = list({*update_fields, 'etat', 'etat_precedent', *CHAMPS_MIROIRS})
        elif not self._state.adding and not etat_modifie and charge is not None:  # colonnes d'état figées
            kwargs['update_fields'] = [f.name for f in self._meta.concrete_fields if not f.primary_key and f.name not in CHAMPS_ETAT]
        super().save(*args, **kwargs)
        self._etat_charge = self.etat

    def refresh_from_db(self, using=None, fields=None, **kwargs):
        super().refresh_from_db(using=using, fields=fields, **kwargs)
        if fields is None or 'etat' in fields:
            self._etat_charge = self.etat

    def _miroirs_actuels(self):
        return {c: getattr(self, c) for c in CHAMPS_MIROIRS}

    def __str__(self):
        return f"{self.nom}"

class Moto(models.Model):
    class Meta:
        verbose_name = _('engin')
        verbose_name_plural = _('engins')

    user = models.ForeignKey(Compte, on_delete=models.RESTRICT, null=True, blank=True)
    structure = models.ForeignKey(to=AssociationMembre, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_('association membre'))
    proprietaire = models.ForeignKey(Membre, on_delete=models.RESTRICT, null=True, blank=True)
    antenne = models.ForeignKey(Antenne, on_delete=models.RESTRICT, null=True, blank=True)
    ville = models.ForeignKey(Ville, on_delete=models.RESTRICT, null=True, blank=True)
    province = models.ForeignKey(Province, on_delete=models.RESTRICT, null=True, blank=True)
    motard_id = models.CharField(max_length=50, null=True, blank=True)
    numero = models.CharField(max_length=20, null=True, blank=True)
    photo = models.ImageField(upload_to='./', null=True, blank=True, validators=[valider_image])
    abonnement = models.DateField()
    num_plaque = models.CharField(max_length=10, null=True, blank=True)
    num_moteur = models.CharField(max_length=50, null=True, blank=True)
    num_chassie = models.CharField(max_length=50, null=True, blank=True)
    marque = models.CharField(max_length=20, null=True, blank=True)
    couleur = models.CharField(max_length=20, null=True, blank=True)
    is_delete = models.BooleanField(default=False)
    mise_a_jour = models.DateField(auto_now=True, null=True, blank=True)
    
    def __str__(self):
        return f"{self.numero}"


class Communique(models.Model):
    user = models.ForeignKey(Compte, on_delete=models.RESTRICT, null=True, blank=True)
    membre = models.ForeignKey(Membre, on_delete=models.RESTRICT, null=True, blank=True)
    message = models.TextField(null=True, blank=True)
    mise_a_jour = models.DateTimeField(auto_now=True, null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.username}: {self.message}"


class Reaction(models.Model):
    user = models.ForeignKey(Compte, on_delete=models.CASCADE, null=True, blank=True)
    membre = models.ForeignKey(Membre, on_delete=models.RESTRICT, null=True, blank=True)
    communique = models.ForeignKey(Communique, on_delete=models.CASCADE, null=True, blank=True)
    reaction = models.TextField(blank=False, null=False)
    mise_a_jour = models.DateTimeField(auto_now=True, null=True, blank=True)


class Famille(models.Model):
    user = models.ForeignKey(Compte, on_delete=models.RESTRICT, null=True, blank=True)
    membre = models.ForeignKey(Membre, on_delete=models.RESTRICT, null=True, blank=True)
    priorite = models.IntegerField(null=True, blank=True)
    beneficiere = models.CharField(max_length=50, null=True, blank=True)
    qualite = models.CharField(max_length=10, null=True, blank=True)
    genre = models.CharField(max_length=20, null=True, blank=True)
    annee = models.IntegerField(null=True, blank=True)

class Notification(models.Model):
    user = models.ForeignKey(Compte, on_delete=models.RESTRICT, null=True, blank=True)
    membre = models.ForeignKey(Membre, on_delete=models.RESTRICT, null=True, blank=True)
    titre = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    is_validate = models.BooleanField(default=False, null=True, blank=True)
    mise_a_jour = models.DateTimeField(auto_now=True, null=True, blank=True)
    
class Error(models.Model):
    user = models.ForeignKey(Compte, on_delete=models.CASCADE, null=True, blank=True)
    error404 = models.BooleanField(default=False, null=True, blank=True)