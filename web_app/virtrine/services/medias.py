"""Médias publics du site (F-60 à F-63) : images converties en WebP avec vignette, PDF publics, APK de l'application mobile.

- ``convertir_webp`` : image validée (types réels JPEG, PNG, WebP ; ``UPLOAD_IMAGE_MAX_MO``), sans métadonnées, réduite, réencodée en WebP,
  avec sa vignette WebP (160 px).
- ``valider_pdf_public`` : PDF réel (``%PDF-``), sans élément actif (``controler_pdf``), taille <= ``UPLOAD_PDF_MAX_MO`` (10 Mo par défaut).
- ``valider_apk`` : archive ZIP réelle contenant ``AndroidManifest.xml``, taille <= ``UPLOAD_APK_MAX_MO`` (80 Mo par défaut).
- ``traiter_fichiers_publics`` : récepteur pre_save des champs marqués ``traitement_propre`` : validation, nom aléatoire, suppression de
  l'ancien fichier remplacé après validation de la transaction.
"""
import io
import uuid
import zipfile

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _
from PIL import ImageOps

from coptapp import validators as v

COTE_MAX = 1600
UPLOAD_PDF_MAX_MO_DEFAUT = 10
UPLOAD_APK_MAX_MO_DEFAUT = 80


def marquer_propre(champ):
    """Marque un champ fichier comme traité par ``traiter_fichiers_publics`` (le récepteur générique de coptapp l'ignore)."""
    champ.traitement_propre = True
    return champ


# ---------------------------------------------------------------- images

def convertir_webp(fichier, cote_max=COTE_MAX):
    """(octets WebP, octets de la vignette WebP) d'une image téléversée ; ValidationError si elle est refusée."""
    v._controler_taille(fichier)
    image, format_reel = v._ouvrir(fichier)
    if format_reel not in v.FORMATS:
        raise ValidationError(_("Format refusé : utilisez une image JPEG, PNG ou WebP."), code='image_format')
    image = v._nettoyer(ImageOps.exif_transpose(image))
    image.thumbnail((cote_max, cote_max))
    principale = v._encoder(image, 'WEBP')
    vignette = image.copy()
    vignette.thumbnail((v.COTE_VIGNETTE, v.COTE_VIGNETTE))
    return principale, v._encoder(vignette, 'WEBP')


def appliquer_webp(instance, champ, champ_vignette=None, cote_max=COTE_MAX):
    """Si `champ` de `instance` porte un NOUVEAU fichier : le convertit en WebP (nom aléatoire) et remplit `champ_vignette` si donné ;
    l'ancien fichier remplacé est supprimé après validation de la transaction. À appeler avant ``super().save()``."""
    fichier = getattr(instance, champ)
    if not fichier or getattr(fichier, '_committed', True):
        return
    champ_modele = instance._meta.get_field(champ)
    ancien = type(instance)._default_manager.filter(pk=instance.pk).values_list(champ, flat=True).first() if instance.pk else None
    ancienne_vignette = None
    if champ_vignette and instance.pk:
        ancienne_vignette = type(instance)._default_manager.filter(pk=instance.pk).values_list(champ_vignette, flat=True).first()
    principale, vignette = convertir_webp(fichier, cote_max)
    nom = uuid.uuid4().hex
    fichier.save(f'{nom}.webp', ContentFile(principale), save=False)
    if champ_vignette:
        getattr(instance, champ_vignette).save(f'{nom}_vignette.webp', ContentFile(vignette), save=False)
    if ancien and ancien != fichier.name:
        v.planifier_suppression(champ_modele.storage, ancien, avec_vignette=True)
    if ancienne_vignette:
        v.planifier_suppression(champ_modele.storage, ancienne_vignette, avec_vignette=False)


# ---------------------------------------------------------------- PDF et APK

def _taille_max(reglage, defaut):
    return int(float(getattr(settings, reglage, defaut)) * 1024 * 1024)


def valider_pdf_public(fichier):
    """Validateur d'un PDF public (charte, règlement, formulaires) : taille <= UPLOAD_PDF_MAX_MO, vrai PDF sans élément actif."""
    if not fichier or getattr(fichier, '_committed', False):
        return
    if fichier.size > _taille_max('UPLOAD_PDF_MAX_MO', UPLOAD_PDF_MAX_MO_DEFAUT):
        raise ValidationError(_("Fichier trop lourd : %(max)s Mo au maximum."), code='pdf_trop_lourd',
                              params={'max': ('%g' % float(getattr(settings, 'UPLOAD_PDF_MAX_MO', UPLOAD_PDF_MAX_MO_DEFAUT))).replace('.', ',')})
    fichier.seek(0)
    debut = fichier.read(1024)
    fichier.seek(0)
    if not debut.lstrip(b'\x00\t\r\n ').startswith(b'%PDF-'):
        raise ValidationError(_("Le fichier n'est pas un PDF."), code='pdf_invalide')
    v.controler_pdf(fichier)


def valider_apk(fichier):
    """Validateur de l'APK : taille <= UPLOAD_APK_MAX_MO, archive ZIP valide qui contient AndroidManifest.xml."""
    if not fichier or getattr(fichier, '_committed', False):
        return
    if fichier.size > _taille_max('UPLOAD_APK_MAX_MO', UPLOAD_APK_MAX_MO_DEFAUT):
        raise ValidationError(_("Fichier trop lourd : %(max)s Mo au maximum."), code='apk_trop_lourd',
                              params={'max': ('%g' % float(getattr(settings, 'UPLOAD_APK_MAX_MO', UPLOAD_APK_MAX_MO_DEFAUT))).replace('.', ',')})
    fichier.seek(0)
    contenu = io.BytesIO(fichier.read())
    fichier.seek(0)
    try:
        with zipfile.ZipFile(contenu) as archive:
            noms = archive.namelist()
            if 'AndroidManifest.xml' not in noms or archive.testzip() is not None:
                raise ValidationError(_("Ce fichier n'est pas une application Android (APK)."), code='apk_invalide')
    except zipfile.BadZipFile:
        raise ValidationError(_("Ce fichier n'est pas une application Android (APK)."), code='apk_invalide')


VALIDATEURS_PUBLICS = {'DocumentPublic.fichier': (valider_pdf_public, 'pdf'), 'Config.apk': (valider_apk, 'apk')}


def traiter_fichiers_publics(sender, instance, **kwargs):
    """Récepteur pre_save : pour chaque champ marqué ``traitement_propre`` qui reçoit un NOUVEAU fichier, valide son contenu, lui donne un
    nom aléatoire (extension imposée) et supprime l'ancien fichier après validation de la transaction."""
    for champ in v._champs_fichiers(sender, images=False, pieces=True):
        if not getattr(champ, 'traitement_propre', False):
            continue
        cle = f'{sender.__name__}.{champ.name}'
        validateur, extension = VALIDATEURS_PUBLICS.get(cle, (None, None))
        fichier = getattr(instance, champ.attname)
        if not fichier or getattr(fichier, '_committed', True) or validateur is None:
            continue
        validateur(fichier)
        ancien = type(instance)._default_manager.filter(pk=instance.pk).values_list(champ.attname, flat=True).first() if instance.pk else None
        fichier.save(f'{uuid.uuid4().hex}.{extension}', fichier.file, save=False)
        if ancien and ancien != fichier.name:
            v.planifier_suppression(champ.storage, ancien, avec_vignette=False)
