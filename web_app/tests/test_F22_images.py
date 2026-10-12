"""F-22 / § 9.2 : validation serveur des images téléversées (type réel, taille, nom aléatoire, redimensionnement)."""
import io
import re

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from coptapp.models import AssociationMembre, Membre, Moto
from coptapp.validators import erreur_image, nom_vignette, valider_image
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
HTML = b'<html><body><script>alert(1)</script></body></html>'


def _image(format_, taille=(10, 10), nom='photo.jpg', mode='RGB'):
    tampon = io.BytesIO()
    Image.new(mode, taille, (200, 30, 30) if mode == 'RGB' else 128).save(tampon, format_)
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type='image/jpeg')


@pytest.fixture(autouse=True)
def media_temporaire(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.mark.parametrize('format_', ['JPEG', 'PNG', 'WEBP'])
def test_F22_formats_acceptes(format_):
    valider_image(_image(format_))


@pytest.mark.parametrize('contenu, nom', [(SVG, 'logo.jpg'), (SVG, 'logo.svg'), (HTML, 'page.jpg'), (HTML, 'page.png'),
                                          (b'GIF89a\x01\x00\x01\x00\x00\x00\x00;', 'anime.jpg'), (b'', 'vide.jpg'),
                                          (b'\xff\xd8\xff\xe0 pas une image', 'casse.jpg')])
def test_F22_faux_fichiers_refuses(contenu, nom):
    fichier = SimpleUploadedFile(nom, contenu, content_type='image/jpeg')
    with pytest.raises(ValidationError):
        valider_image(fichier)
    assert erreur_image(fichier)


def test_F22_gif_reel_refuse_car_hors_liste():
    assert erreur_image(_image('GIF'))


def test_F22_taille_maximale_configurable(settings):
    fichier = _image('PNG', (400, 400))
    assert erreur_image(fichier) is None
    settings.UPLOAD_IMAGE_MAX_MO = 0.0001
    assert 'lourde' in erreur_image(fichier)


def test_F22_traitement_nom_aleatoire_extension_imposee_et_reduction(jeu, media_temporaire):
    # contenu PNG envoyé sous le nom « .jpg » : l'extension est celle du format réel
    fichier = _image('PNG', (3000, 2000), nom='moi.jpg')
    jeu['membre'].photo = fichier
    jeu['membre'].save()
    nom = jeu['membre'].photo.name
    assert re.fullmatch(r'[0-9a-f]{32}\.png', nom), nom
    assert 'moi' not in nom
    with Image.open(jeu['membre'].photo.path) as image:
        assert image.format == 'PNG' and max(image.size) == 1200
    with Image.open(media_temporaire / nom_vignette(nom)) as vignette:
        assert max(vignette.size) == 160


def test_F22_deux_envois_ont_deux_noms_differents(jeu):
    for _ in range(2):
        Moto.objects.create(proprietaire=jeu['membre'], abonnement=jeu['moto'].abonnement, photo=_image('JPEG'))
    noms = set(Moto.objects.exclude(photo='').values_list('photo', flat=True))
    assert len(noms) == 2


def test_F22_exif_supprime(jeu):
    tampon = io.BytesIO()
    image = Image.new('RGB', (50, 50), (1, 2, 3))
    exif = Image.Exif()
    exif[0x010F] = 'Appareil secret'
    image.save(tampon, 'JPEG', exif=exif)
    jeu['membre'].photo = SimpleUploadedFile('a.jpg', tampon.getvalue())
    jeu['membre'].save()
    with Image.open(jeu['membre'].photo.path) as stockee:
        assert 0x010F not in stockee.getexif()


def test_F22_enregistrement_direct_d_un_svg_leve_une_erreur(jeu):
    association = jeu['association']
    association.logo = SimpleUploadedFile('logo.jpg', SVG, content_type='image/jpeg')
    with pytest.raises(ValidationError):
        association.save()
    association.refresh_from_db()
    assert not association.logo


def test_F22_validateur_branche_sur_les_champs(jeu):
    association = AssociationMembre(nom='X', logo=SimpleUploadedFile('x.jpg', HTML, content_type='image/jpeg'))
    with pytest.raises(ValidationError) as erreur:
        association.full_clean(exclude=['num_justice'])
    assert 'logo' in erreur.value.message_dict


def test_F22_fichier_deja_enregistre_non_revalide(jeu, settings):
    jeu['membre'].photo = _image('JPEG', (400, 400))
    jeu['membre'].save()
    settings.UPLOAD_IMAGE_MAX_MO = 0.0000001
    jeu['membre'].full_clean(exclude=['password'])  # le fichier existant n'est pas contrôlé à nouveau


def test_F22_vue_modifier_engin_refuse_un_svg_deguise(client, jeu):
    client.force_login(jeu['compte'])
    donnees = {k: 'x' for k in ('plaque', 'chassie', 'moteur', 'marque', 'couleur')}
    r = client.post(reverse('edit-moto', args=[jeu['moto'].id]),
                    {**donnees, 'photo': SimpleUploadedFile('moto.jpg', SVG, content_type='image/jpeg')})
    assert r.status_code == 400
    jeu['moto'].refresh_from_db()
    assert not jeu['moto'].photo and jeu['moto'].marque != 'x'


def test_F22_vue_modifier_engin_accepte_une_vraie_image(client, jeu):
    client.force_login(jeu['compte'])
    donnees = {k: 'x' for k in ('plaque', 'chassie', 'moteur', 'marque', 'couleur')}
    r = client.post(reverse('edit-moto', args=[jeu['moto'].id]), {**donnees, 'photo': _image('JPEG', (2000, 1000))})
    assert r.status_code == 200
    jeu['moto'].refresh_from_db()
    assert re.fullmatch(r'[0-9a-f]{32}\.jpg', jeu['moto'].photo.name)


def test_F22_vue_article_refuse_html_deguise(client, jeu):
    from virtrine.models import Article
    client.force_login(jeu['compte'])
    r = client.post(reverse('article', args=[jeu['article'].id]),
                    {'titre': 'Nouveau', 'description': 'd', 'image': SimpleUploadedFile('a.jpg', HTML, content_type='image/jpeg')})
    assert r.status_code == 400
    assert Article.objects.get(id=jeu['article'].id).titre == 'Article fictif'
