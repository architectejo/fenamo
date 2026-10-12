"""Validation et traitement des images téléversées (cahier des charges web § 9.2 et F-22).

- `valider_image` : validateur réutilisable (``validators=[valider_image]`` sur un champ, ou appel direct dans une
  vue qui affecte un fichier à la main). Contrôle la taille et le TYPE RÉEL avec Pillow (JPEG, PNG, WebP) ; un SVG,
  un HTML ou tout autre fichier renommé en .jpg est refusé. L'extension envoyée n'est jamais crue.
- `traiter_image` : réencode l'image (métadonnées EXIF supprimées), impose l'extension du format réel, donne un nom
  aléatoire, réduit à 1200 px de côté au plus et fabrique une vignette de 160 px.
- `traiter_images_avant_enregistrement` : récepteur ``pre_save`` branché sur les modèles qui portent des images
  (voir ``coptapp.apps``) : tout nouveau fichier image est ainsi traité, y compris quand une vue l'affecte directement.

Réglage : ``UPLOAD_IMAGE_MAX_MO`` (variable d'environnement, 3 par défaut).
"""
import io
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps, UnidentifiedImageError

# Format réel détecté par Pillow -> extension imposée.
FORMATS = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}
COTE_MAX = 1200
COTE_VIGNETTE = 160
PIXELS_MAX = 50_000_000  # au-delà : bombe de décompression probable
# Pièces à lire en détail (scans) ou fonds d'écran : côté maximal plus grand, par nom de champ.
COTE_MAX_PAR_CHAMP = {'capture_justice': 2000, 'preuve_de_paiement': 2000, 'image_background': 1920}
SUFFIXE_VIGNETTE = '_vignette'


def taille_max_octets():
    return int(float(getattr(settings, 'UPLOAD_IMAGE_MAX_MO', 3)) * 1024 * 1024)


def _ouvrir(fichier):
    """Ouvre `fichier` avec Pillow après vérification d'intégrité ; retourne (image rechargée, format réel)."""
    try:
        fichier.seek(0)
        with Image.open(fichier) as image:
            if image.width * image.height > PIXELS_MAX:
                raise ValidationError(_("Image trop grande (nombre de pixels)."), code='image_trop_grande')
            format_reel = image.format
            image.verify()
        fichier.seek(0)
        image = Image.open(fichier)  # verify() rend l'objet inutilisable : on rouvre
        image.load()
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError, Image.DecompressionBombError):
        raise ValidationError(_("Le fichier n'est pas une image valide (JPEG, PNG ou WebP)."), code='image_invalide')
    finally:
        try:
            fichier.seek(0)
        except (OSError, ValueError):
            pass  # fichier déjà fermé : rien à repositionner
    return image, format_reel


def valider_image(fichier):
    """Validateur Django : taille <= UPLOAD_IMAGE_MAX_MO et type réel JPEG / PNG / WebP.

    Un fichier déjà enregistré (non remplacé) n'est pas revalidé.
    """
    if not fichier or getattr(fichier, '_committed', False):
        return
    if fichier.size > taille_max_octets():
        raise ValidationError(
            _("Image trop lourde : %(max)s Mo au maximum."), code='image_trop_lourde',
            params={'max': ('%g' % float(getattr(settings, 'UPLOAD_IMAGE_MAX_MO', 3))).replace('.', ',')},
        )
    format_reel = _ouvrir(fichier)[1]
    if format_reel not in FORMATS:
        raise ValidationError(_("Format refusé : utilisez une image JPEG, PNG ou WebP."), code='image_format')


def _encoder(image, format_reel):
    tampon = io.BytesIO()
    if format_reel == 'JPEG':
        image.convert('RGB').save(tampon, 'JPEG', quality=85, optimize=True)
    elif format_reel == 'PNG':
        image.save(tampon, 'PNG', optimize=True)
    else:
        image.save(tampon, 'WEBP', quality=85)
    return tampon.getvalue()


def traiter_image(fichier, cote_max=COTE_MAX):
    """Image réencodée, réduite, sans métadonnées. Retourne (octets, octets de la vignette, extension).

    Lève ValidationError si le fichier n'est pas une image acceptée (le fichier est revalidé ici).
    """
    valider_image(fichier)
    image, format_reel = _ouvrir(fichier)
    if format_reel not in FORMATS:
        raise ValidationError(_("Format refusé : utilisez une image JPEG, PNG ou WebP."), code='image_format')
    image = ImageOps.exif_transpose(image)
    image.thumbnail((cote_max, cote_max))
    principale = _encoder(image, format_reel)
    vignette = image.copy()
    vignette.thumbnail((COTE_VIGNETTE, COTE_VIGNETTE))
    return principale, _encoder(vignette, format_reel), FORMATS[format_reel]


def nom_vignette(nom):
    """Nom de la vignette stockée à côté de l'image `nom` : ``abc.jpg`` -> ``abc_vignette.jpg``."""
    racine, _point, extension = nom.rpartition('.')
    return f'{racine}{SUFFIXE_VIGNETTE}.{extension}' if racine else f'{nom}{SUFFIXE_VIGNETTE}'


def traiter_images_avant_enregistrement(sender, instance, **kwargs):
    """Récepteur pre_save : traite chaque nouveau fichier des ImageField de `instance`."""
    for champ in instance._meta.concrete_fields:
        if not isinstance(champ, models.ImageField):
            continue
        fichier = getattr(instance, champ.attname)
        if not fichier or getattr(fichier, '_committed', True):
            continue
        principale, vignette, extension = traiter_image(fichier, COTE_MAX_PAR_CHAMP.get(champ.name, COTE_MAX))
        racine = uuid.uuid4().hex
        fichier.save(f'{racine}.{extension}', ContentFile(principale), save=False)
        champ.storage.save(nom_vignette(fichier.name), ContentFile(vignette))


def erreur_image(fichier):
    """Message d'erreur (texte) si `fichier` est refusé par `valider_image`, sinon None. Pour les vues qui affectent un
    fichier à la main (hors formulaire) : à appeler AVANT toute modification des données."""
    try:
        valider_image(fichier)
    except ValidationError as erreur:
        return ' '.join(erreur.messages)
    return None
