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
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps, UnidentifiedImageError

# Format réel détecté par Pillow -> extension imposée.
FORMATS = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}
COTE_MAX = 1200
COTE_VIGNETTE = 160
PIXELS_MAX = 25_000_000  # au-delà : bombe de décompression probable (un appareil de 24 Mpx passe)
# Pièces à lire en détail (scans) ou fonds d'écran : côté maximal plus grand, par nom de champ.
COTE_MAX_PAR_CHAMP = {'capture_justice': 2000, 'preuve_de_paiement': 2000, 'image_background': 1920}
SUFFIXE_VIGNETTE = '_vignette'


def taille_max_octets():
    return int(float(getattr(settings, 'UPLOAD_IMAGE_MAX_MO', 3)) * 1024 * 1024)


def _ouvrir(fichier):
    """Ouvre et décode `fichier` UNE fois avec Pillow ; retourne (image décodée, format réel normalisé).

    Un MPO (JPEG multi-images des téléphones) est ramené à JPEG. Les dimensions sont contrôlées avant le décodage.
    """
    try:
        fichier.seek(0)
        image = Image.open(fichier)
        if image.width * image.height > PIXELS_MAX:
            raise ValidationError(_("Image trop grande (nombre de pixels)."), code='image_trop_grande')
        format_reel = 'JPEG' if image.format == 'MPO' else image.format
        image.load()  # décode : une image tronquée ou piégée échoue ici
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


def _controler_taille(fichier):
    if fichier.size > taille_max_octets():
        raise ValidationError(
            _("Image trop lourde : %(max)s Mo au maximum."), code='image_trop_lourde',
            params={'max': ('%g' % float(getattr(settings, 'UPLOAD_IMAGE_MAX_MO', 3))).replace('.', ',')},
        )


def valider_image(fichier):
    """Validateur Django : taille <= UPLOAD_IMAGE_MAX_MO et type réel JPEG / PNG / WebP.

    Un fichier déjà enregistré (non remplacé) n'est pas revalidé.
    """
    if not fichier or getattr(fichier, '_committed', False):
        return
    _controler_taille(fichier)
    format_reel = _ouvrir(fichier)[1]
    if format_reel not in FORMATS:
        raise ValidationError(_("Format refusé : utilisez une image JPEG, PNG ou WebP."), code='image_format')


def _nettoyer(image):
    """Copie de `image` SANS aucune métadonnée (EXIF, commentaire JPEG, segments APP, textes PNG) : seuls les pixels passent."""
    mode = image.mode if image.mode in ('RGB', 'RGBA', 'L', 'LA') else ('RGBA' if 'A' in image.getbands() or 'transparency' in image.info else 'RGB')
    source = image.convert(mode) if image.mode != mode else image
    return Image.frombytes(mode, source.size, source.tobytes())


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

    Contrôle la taille et le type réel puis décode UNE fois. Lève ValidationError si l'image est refusée.
    """
    _controler_taille(fichier)
    image, format_reel = _ouvrir(fichier)
    if format_reel not in FORMATS:
        raise ValidationError(_("Format refusé : utilisez une image JPEG, PNG ou WebP."), code='image_format')
    image = _nettoyer(ImageOps.exif_transpose(image))
    image.thumbnail((cote_max, cote_max))
    principale = _encoder(image, format_reel)
    vignette = image.copy()
    vignette.thumbnail((COTE_VIGNETTE, COTE_VIGNETTE))
    return principale, _encoder(vignette, format_reel), FORMATS[format_reel]


def nom_vignette(nom):
    """Nom de la vignette stockée à côté de l'image `nom` : ``abc.jpg`` -> ``abc_vignette.jpg``."""
    racine, _point, extension = nom.rpartition('.')
    return f'{racine}{SUFFIXE_VIGNETTE}.{extension}' if racine else f'{nom}{SUFFIXE_VIGNETTE}'


def _champs_fichiers(modele, images=True, pieces=True):
    for champ in modele._meta.concrete_fields:
        if isinstance(champ, models.ImageField):
            if images:
                yield champ
        elif isinstance(champ, models.FileField) and pieces:
            yield champ


def _encore_utilise(nom):
    """Vrai si un autre enregistrement (de n'importe quel modèle à fichiers) référence encore `nom`."""
    from django.apps import apps
    for modele in apps.get_models():
        for champ in _champs_fichiers(modele):
            if modele._default_manager.filter(**{champ.attname: nom}).exists():
                return True
    return False


def planifier_suppression(stockage, nom, avec_vignette=True):
    """Supprime le fichier `nom` (et sa vignette) APRÈS validation de la transaction, s'il n'est plus utilisé."""
    if not nom:
        return

    def supprimer():
        if _encore_utilise(nom):
            return
        for cible in ((nom, nom_vignette(nom)) if avec_vignette else (nom,)):
            stockage.delete(cible)  # ne lève rien si le fichier n'existe plus

    transaction.on_commit(supprimer)


def _anciens_fichiers(sender, instance, champs):
    """{attname: ancien nom} des champs de `instance` enregistrés en base (vide pour une nouvelle ligne)."""
    if not instance.pk:
        return {}
    return sender._default_manager.filter(pk=instance.pk).values(*[c.attname for c in champs]).first() or {}


def _traiter_fichiers(sender, instance, images):
    champs = list(_champs_fichiers(sender, images=images, pieces=not images))
    anciens = None
    for champ in champs:
        fichier = getattr(instance, champ.attname)
        nouveau = bool(fichier) and not getattr(fichier, '_committed', True)
        if fichier and not nouveau:
            continue
        if nouveau:
            if images:
                principale, vignette, extension = traiter_image(fichier, COTE_MAX_PAR_CHAMP.get(champ.name, COTE_MAX))
                fichier.save(f'{uuid.uuid4().hex}.{extension}', ContentFile(principale), save=False)
                champ.storage.save(nom_vignette(fichier.name), ContentFile(vignette))
            else:
                valider_piece(fichier)
                fichier.save(f'{uuid.uuid4().hex}.{type_reel_piece(fichier)}', fichier.file, save=False)
        if anciens is None:
            anciens = _anciens_fichiers(sender, instance, champs)
        ancien = anciens.get(champ.attname)
        if ancien and ancien != (fichier.name if fichier else None):
            planifier_suppression(champ.storage, ancien, avec_vignette=images)


def traiter_images_avant_enregistrement(sender, instance, **kwargs):
    """Récepteur pre_save : traite chaque nouveau fichier des ImageField de `instance` (type réel, nom aléatoire,
    1200 px, vignette) et supprime, après validation de la transaction, l'ancien fichier remplacé ou retiré."""
    _traiter_fichiers(sender, instance, images=True)


def supprimer_fichiers_apres_suppression(sender, instance, **kwargs):
    """Récepteur post_delete : supprime les fichiers de la ligne effacée, après validation de la transaction."""
    for champ in _champs_fichiers(sender):
        planifier_suppression(champ.storage, getattr(instance, champ.attname).name or None,
                              avec_vignette=isinstance(champ, models.ImageField))


def erreur_image(fichier):
    """Message d'erreur (texte) si `fichier` est refusé par `valider_image`, sinon None. Pour les vues qui affectent un
    fichier à la main (hors formulaire) : à appeler AVANT toute modification des données."""
    try:
        valider_image(fichier)
    except ValidationError as erreur:
        return ' '.join(erreur.messages)
    return None


# ---------------------------------------------------------------- pièces jointes (PDF, JPEG, PNG)

EXTENSIONS_PIECES = {'pdf': 'pdf', 'JPEG': 'jpg', 'PNG': 'png'}


def taille_max_piece_octets():
    return int(float(getattr(settings, 'UPLOAD_PIECE_MAX_MO', 3)) * 1024 * 1024)


def type_reel_piece(fichier):
    """Extension imposée ('pdf', 'jpg' ou 'png') d'après le CONTENU du fichier ; ValidationError sinon."""
    fichier.seek(0)
    debut = fichier.read(1024)
    fichier.seek(0)
    if debut.lstrip(b'\x00\t\r\n ').startswith(b'%PDF-'):
        return 'pdf'
    format_reel = _ouvrir(fichier)[1]
    if format_reel in ('JPEG', 'PNG'):
        return EXTENSIONS_PIECES[format_reel]
    raise ValidationError(_("Format refusé : utilisez un PDF, une image JPEG ou PNG."), code='piece_format')


def valider_piece(fichier):
    """Validateur d'une pièce jointe (fiche d'identité…) : taille <= UPLOAD_PIECE_MAX_MO, type réel PDF / JPEG / PNG."""
    if not fichier or getattr(fichier, '_committed', False):
        return
    if fichier.size > taille_max_piece_octets():
        raise ValidationError(
            _("Fichier trop lourd : %(max)s Mo au maximum."), code='piece_trop_lourde',
            params={'max': ('%g' % float(getattr(settings, 'UPLOAD_PIECE_MAX_MO', 3))).replace('.', ',')},
        )
    type_reel_piece(fichier)


def erreur_piece(fichier):
    """Comme `erreur_image`, pour une pièce jointe."""
    try:
        valider_piece(fichier)
    except ValidationError as erreur:
        return ' '.join(erreur.messages)
    return None


def traiter_pieces_avant_enregistrement(sender, instance, **kwargs):
    """Récepteur pre_save des FileField qui ne sont pas des images : valide, impose l'extension, nom aléatoire,
    et supprime après validation de la transaction l'ancien fichier remplacé ou retiré."""
    _traiter_fichiers(sender, instance, images=False)
