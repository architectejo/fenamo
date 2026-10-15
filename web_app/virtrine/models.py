from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from compte.models import Compte
from coptapp.validators import valider_image
from virtrine.services.html_propre import nettoyer_html
from virtrine.services.medias import appliquer_webp, marquer_propre, valider_apk, valider_pdf_public

LANGUES_SITE = (('ln', _('Lingala')), ('sw', _('Kiswahili')), ('lua', _('Tshiluba')), ('kg', _('Kikongo')))
HOTES_VIDEO = frozenset({'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be', 'facebook.com', 'www.facebook.com', 'm.facebook.com', 'fb.watch'})


def valider_lien_video(valeur):
    """Lien YouTube ou Facebook en https seulement : le site en fait un lecteur ; aucun code d'intégration n'est jamais accepté ni exposé."""
    if not valeur:
        return
    morceaux = urlsplit(valeur)
    if morceaux.scheme != 'https' or (morceaux.hostname or '').lower() not in HOTES_VIDEO:
        raise ValidationError(_("Indiquez un lien https vers une vidéo YouTube ou Facebook."), code='lien_video')


class Galery(models.Model):
    """Image d'article (``principale``) et élément de la galerie publique (F-60) : photo ou vidéo (lien seul)."""

    class Type(models.TextChoices):
        PHOTO = 'photo', _('Photo')
        VIDEO = 'video', _('Vidéo')

    principale = models.BooleanField(default=False, null=True, blank=True)
    image = models.ImageField(upload_to="./article", null=True, blank=True, validators=[valider_image])
    is_delete = models.BooleanField(default=False, null=True, blank=True)
    type = models.CharField(max_length=5, choices=Type.choices, default=Type.PHOTO)
    legende = models.CharField(max_length=200, blank=True, default='')
    lien_video = models.URLField(max_length=300, blank=True, default='', validators=[valider_lien_video])
    date = models.DateField(null=True, blank=True)
    ordre = models.PositiveSmallIntegerField(default=0)
    publie = models.BooleanField(default=False)  # rien n'est publié automatiquement
    vignette = marquer_propre(models.ImageField(upload_to="./article", null=True, blank=True))

    def save(self, *args, **kwargs):
        appliquer_webp(self, 'image', 'vignette')
        super().save(*args, **kwargs)


class Article(models.Model):
    """Article ou communiqué du site (F-60). Le français est porté par l'article lui-même (``titre``, ``resume``, ``description`` = texte) ;
    les autres langues par ``ArticleTraduction``. ``integration_code`` est conservé en base mais n'est plus jamais exposé ni saisi."""

    class Type(models.TextChoices):
        ARTICLE = 'article', _('Article')
        COMMUNIQUE = 'communique', _('Communiqué')

    class Statut(models.TextChoices):
        BROUILLON = 'brouillon', _('Brouillon')
        PUBLIE = 'publie', _('Publié')

    user = models.ForeignKey(Compte, on_delete=models.RESTRICT, null=True, blank=True)
    titre = models.CharField(max_length=200, null=True, blank=True)
    image = models.ImageField(upload_to='./article', null=True, blank=True, validators=[valider_image])
    integration_code = models.TextField(null=True, blank=True)
    galery = models.ManyToManyField(to=Galery, related_name="Images_article")
    description = models.TextField(blank=True, null=True)
    mise_a_jour = models.DateTimeField(auto_now=True, null=True, blank=True)
    slug = models.SlugField(max_length=200, unique=True, null=True, blank=True)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.ARTICLE)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON, db_index=True)
    date_publication = models.DateTimeField(null=True, blank=True)
    resume = models.CharField(max_length=300, blank=True, default='')
    lien_video = models.URLField(max_length=300, blank=True, default='', validators=[valider_lien_video])

    def __str__(self):
        return self.titre or f'Article {self.pk}'

    def generer_slug(self):
        """Slug unique tiré du titre (suffixe numérique en cas de doublon) ; ne change plus une fois attribué."""
        base = slugify(self.titre or '')[:170] or 'article'
        slug, n = base, 1
        while Article.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            n += 1
            slug = f'{base}-{n}'
        return slug

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.generer_slug()
        self.description = nettoyer_html(self.description)  # liste blanche à l'enregistrement
        appliquer_webp(self, 'image')
        super().save(*args, **kwargs)


class ArticleTraduction(models.Model):
    """Traduction d'un article (lingala, kiswahili, tshiluba, kikongo) ; sans traduction, le site affiche le français."""

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='traductions')
    langue = models.CharField(max_length=3, choices=LANGUES_SITE)
    titre = models.CharField(max_length=200)
    resume = models.CharField(max_length=300, blank=True, default='')
    texte = models.TextField(blank=True, default='')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['article', 'langue'], name='traduction_unique_par_langue')]

    def __str__(self):
        return f'{self.article_id} ({self.langue})'

    def save(self, *args, **kwargs):
        self.texte = nettoyer_html(self.texte)
        super().save(*args, **kwargs)


class Config(models.Model):
    nom = models.CharField(max_length=500, null=True, blank=True)
    image_background = models.ImageField(upload_to="./", null=True, blank=True, validators=[valider_image])
    logo = models.ImageField(upload_to="./", null=True, blank=True, validators=[valider_image])
    slogant = models.CharField(max_length=500, null=True, blank=True)
    welcome_text = models.CharField(max_length=200, null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    adresse = models.TextField(null=True, blank=True)
    facebook = models.CharField(max_length=255, null=True, blank=True)
    twitter = models.CharField(max_length=255, null=True, blank=True)
    youtube = models.CharField(max_length=255, null=True, blank=True)
    gmail = models.EmailField(max_length=255, null=True, blank=True)
    instagram = models.CharField(max_length=255, null=True, blank=True)
    linkedin = models.CharField(max_length=255, null=True, blank=True)
    phone1 = models.CharField(max_length=20, null=True, blank=True)
    phone2 = models.CharField(max_length=20, null=True, blank=True)
    phone3 = models.CharField(max_length=20, null=True, blank=True)
    phone4 = models.CharField(max_length=20, null=True, blank=True)
    phone5 = models.CharField(max_length=20, null=True, blank=True)
    phone6 = models.CharField(max_length=20, null=True, blank=True)
    phone7 = models.CharField(max_length=20, null=True, blank=True)
    partenaire1 = models.CharField(max_length=255, null=True, blank=True)
    link1 = models.CharField(max_length=255, null=True, blank=True)
    partenaire2 = models.CharField(max_length=255, null=True, blank=True)
    link2 = models.CharField(max_length=255, null=True, blank=True)
    partenaire3 = models.CharField(max_length=255, null=True, blank=True)
    link3 = models.CharField(max_length=255, null=True, blank=True)
    partenaire4 = models.CharField(max_length=255, null=True, blank=True)
    link4 = models.CharField(max_length=255, null=True, blank=True)
    partenaire5 = models.CharField(max_length=255, null=True, blank=True)
    link5 = models.CharField(max_length=255, null=True, blank=True)
    partenaire6 = models.CharField(max_length=255, null=True, blank=True)
    link6 = models.CharField(max_length=255, null=True, blank=True)
    partenaire7 = models.CharField(max_length=255, null=True, blank=True)
    link7 = models.CharField(max_length=255, null=True, blank=True)
    # Les anciennes colonnes phone1..7, partenaire1..7 et link1..7 sont gardées (migration additive) : TelephoneSite et Partenaire les remplacent.
    langues_actives = models.CharField(max_length=40, default='fr', help_text=_("codes séparés par des virgules ; le français est toujours actif (F-64)"))
    # Le site affiche soit un jeu d'EXEMPLE fixe (faux, par défaut), soit les données réelles de l'application web (vrai). SU seul.
    donnees_reelles_actif = models.BooleanField(default=False)
    paiement_en_ligne_actif = models.BooleanField(default=False)  # F-65 : désactivé par défaut, changement journalisé, SU seul
    apk = marquer_propre(models.FileField(upload_to='application/', null=True, blank=True, validators=[valider_apk]))
    apk_version = models.CharField(max_length=30, blank=True, default='')
    apk_date = models.DateField(null=True, blank=True)
    apk_notice = models.TextField(blank=True, default='')

    @classmethod
    def instance(cls):
        """La configuration du site : une seule ligne, créée à la demande (jamais de doublon)."""
        return cls.objects.order_by('pk').first() or cls.objects.create()

    def save(self, *args, **kwargs):
        if not self.pk and Config.objects.exists():
            raise ValidationError(_("La configuration du site est unique : modifiez l'existante."))
        super().save(*args, **kwargs)

    def langues(self):
        """Langues actives : le français d'abord, puis les langues nationales reconnues, sans doublon."""
        codes = [c.strip() for c in (self.langues_actives or '').split(',')]
        valides = [code for code, _nom in LANGUES_SITE]
        return ['fr'] + [c for c in valides if c in codes]


class TelephoneSite(models.Model):
    """Téléphone affiché sur le site (remplace phone1..7 de Config)."""
    numero = models.CharField(max_length=25)
    libelle = models.CharField(max_length=60, blank=True, default='')
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'pk']

    def __str__(self):
        return self.numero


class Partenaire(models.Model):
    """Partenaire affiché dans le pied de page (remplace partenaire1..7 et link1..7 de Config)."""
    nom = models.CharField(max_length=255)
    lien = models.URLField(max_length=255, blank=True, default='')
    logo = models.ImageField(upload_to='partenaires/', null=True, blank=True, validators=[valider_image])
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'pk']

    def __str__(self):
        return self.nom


class DocumentPublic(models.Model):
    """Document PDF à télécharger (charte, règlement d'ordre intérieur, formulaires)."""

    class Type(models.TextChoices):
        CHARTE = 'charte', _('Charte')
        ROI = 'roi', _("Règlement d'ordre intérieur")
        AUTRE = 'autre', _('Autre')

    titre = models.CharField(max_length=200)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.AUTRE)
    fichier = marquer_propre(models.FileField(upload_to='documents/', validators=[valider_pdf_public]))
    date = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ['-date', '-pk']

    def __str__(self):
        return self.titre


class MembreComite(models.Model):
    """Dirigeant publié sur la page « Comité exécutif » : sans lien vers ``Membre`` (aucune donnée personnelle interne n'est exposée)."""
    nom = models.CharField(max_length=150)
    fonction = models.CharField(max_length=150)
    fonction_code = models.CharField(max_length=30, blank=True, default='')
    photo = models.ImageField(upload_to='comite/', null=True, blank=True, validators=[valider_image])
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'pk']

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        appliquer_webp(self, 'photo', cote_max=800)
        super().save(*args, **kwargs)


class Contact(models.Model):
    nom = models.CharField(max_length=100, null=True, blank=True)
    mail = models.EmailField(null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    raison = models.CharField(max_length=100, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    traiter = models.BooleanField(default=False, null=True, blank=True)
    mise_a_jour = models.DateTimeField(auto_now=True, null=True, blank=True)
    # F-62 (ajouts additifs) : horodatage de réception, auteur et date du marquage « traité ». Texte brut seulement (aucun HTML).
    cree_le = models.DateTimeField(null=True, blank=True, default=timezone.now)
    traite_par = models.ForeignKey('compte.Compte', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    traite_le = models.DateTimeField(null=True, blank=True)