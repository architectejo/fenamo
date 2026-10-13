"""Validation indépendante des images téléversées (F-22) via les vues : fiche membre et inscription mobapp.

Refus propre (400, jamais 500, données inchangées) ; fichier valide : nom aléatoire, EXIF retiré, vignette créée.
"""
import io
import os
import re

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from coptapp.models import Membre
from coptapp.validators import nom_vignette
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

CHAMPS = ('nom about genre titre fonction comite nation brevet etat_civil epouse adresse telephone mail categorie '
          'permis qualite autre_asbl numero_carte_d_electeur numero_carte_de_membre nom_pere nom_mere village '
          'chefferie territoire province_origine').split()


@pytest.fixture(autouse=True)
def media_temporaire(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.PRIVATE_MEDIA_ROOT = tmp_path  # même dossier : les tests lisent les fichiers à un seul endroit
    return tmp_path


def _octets(format_, taille=(20, 20), mode='RGB', **kw):
    tampon = io.BytesIO()
    Image.new(mode, taille, 1 if mode == '1' else (10, 120, 200)).save(tampon, format_, **kw)
    return tampon.getvalue()


def _fichier(contenu, nom='photo.jpg'):
    return SimpleUploadedFile(nom, contenu, content_type='image/jpeg')


def _post_modifier(client, jeu, photo):
    d = {c: 'x' for c in CHAMPS}
    d.update({'nom': 'Nom photo', 'date': '02-03-1991', 'modifier': '1', 'mail': 'a@example.invalid', 'photo': photo})
    return client.post(reverse('membre-view', args=[jeu['membre'].id]), d)


def _fichiers_ecrits(dossier):
    return [f for f in os.listdir(dossier)]


# ---------------------------------------------------------------- refus propres

POLYGLOTTE = _octets('JPEG') + b'<html><script>alert(1)</script></html>'

REFUSES = {
    'svg': (b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', 'a.svg'),
    'svg_deguise_jpg': (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', 'a.jpg'),
    'html': (b'<html><script>alert(1)</script></html>', 'a.jpg'),
    'gif_reel': (_octets('GIF'), 'a.gif'),
    'gif_deguise_jpg': (_octets('GIF'), 'a.jpg'),
    'bmp': (_octets('BMP'), 'a.jpg'),
    'texte': (b'hello', 'a.png'),
    'vide': (b'', 'a.jpg'),
    'jpeg_tronque': (_octets('JPEG', (400, 400))[:60], 'a.jpg'),
    'php': (b'<?php system($_GET["c"]); ?>', 'a.php.jpg'),
}


@pytest.mark.parametrize('cle', list(REFUSES))
def test_F22_fiche_refuse_proprement(client, jeu, cle, media_temporaire):
    contenu, nom = REFUSES[cle]
    client.force_login(jeu['compte'])
    r = _post_modifier(client, jeu, _fichier(contenu, nom))
    assert r.status_code == 400
    jeu['membre'].refresh_from_db()
    assert jeu['membre'].nom == 'Membre Fictif' and not jeu['membre'].photo
    assert _fichiers_ecrits(media_temporaire) == []  # rien d'écrit sur le disque


def test_F22_fiche_trop_lourde(client, jeu, settings, media_temporaire):
    settings.UPLOAD_IMAGE_MAX_MO = 0.01
    gros = _octets('PNG', (600, 600), mode='RGB')
    # PNG incompressible pour dépasser 10 Ko
    bruit = Image.frombytes('RGB', (200, 200), os.urandom(200 * 200 * 3))
    tampon = io.BytesIO()
    bruit.save(tampon, 'PNG')
    assert len(tampon.getvalue()) > 10_500
    client.force_login(jeu['compte'])
    r = _post_modifier(client, jeu, _fichier(tampon.getvalue(), 'gros.png'))
    assert r.status_code == 400 and 'lourde' in r.content.decode()
    jeu['membre'].refresh_from_db()
    assert not jeu['membre'].photo
    del gros


def test_F22_fiche_bombe_de_decompression_png(client, jeu, media_temporaire):
    """400 millions de pixels dans quelques ko : refus propre, pas de 500 ni d'allocation géante."""
    contenu = _octets('PNG', (20000, 20000), mode='1')
    assert len(contenu) < 1_000_000
    client.force_login(jeu['compte'])
    r = _post_modifier(client, jeu, _fichier(contenu, 'bombe.png'))
    assert r.status_code == 400
    assert _fichiers_ecrits(media_temporaire) == []


def test_F22_fiche_dimension_geante_entre_les_deux_seuils(client, jeu, media_temporaire):
    """Entre 50 millions de pixels (seuil de l'application) et MAX_IMAGE_PIXELS de Pillow : refusé aussi."""
    contenu = _octets('PNG', (9000, 9000), mode='1')  # 81 M pixels
    client.force_login(jeu['compte'])
    r = _post_modifier(client, jeu, _fichier(contenu, 'grande.png'))
    assert r.status_code == 400 and _fichiers_ecrits(media_temporaire) == []


def test_F22_fiche_bombe_via_modele_leve_validation_error(jeu):
    from django.core.exceptions import ValidationError
    jeu['membre'].photo = _fichier(_octets('PNG', (20000, 20000), mode='1'), 'b.png')
    with pytest.raises(ValidationError):
        jeu['membre'].save()


# ---------------------------------------------------------------- polyglotte

def test_F22_polyglotte_jpeg_html_est_reencode_sans_html(client, jeu, media_temporaire):
    """Un JPEG valide suivi de HTML est accepté en tant que JPEG mais le HTML ne survit pas au réencodage."""
    client.force_login(jeu['compte'])
    r = _post_modifier(client, jeu, _fichier(POLYGLOTTE, 'poly.jpg'))
    assert r.status_code in (200, 400)
    for nom in _fichiers_ecrits(media_temporaire):
        brut = (media_temporaire / nom).read_bytes()
        assert b'<script' not in brut and b'<html' not in brut
        with Image.open(media_temporaire / nom) as image:
            assert image.format in ('JPEG', 'PNG', 'WEBP')


def test_F22_polyglotte_commentaire_jpeg_html_supprime(client, jeu, media_temporaire):
    tampon = io.BytesIO()
    Image.new('RGB', (30, 30), (5, 5, 5)).save(tampon, 'JPEG', comment=b'<script>alert(1)</script>')
    client.force_login(jeu['compte'])
    _post_modifier(client, jeu, _fichier(tampon.getvalue(), 'c.jpg'))
    jeu['membre'].refresh_from_db()
    assert jeu['membre'].photo
    assert b'<script' not in open(jeu['membre'].photo.path, 'rb').read()


# ---------------------------------------------------------------- fichier valide

def test_F22_fiche_fichier_valide_nom_aleatoire_exif_retire_vignette(client, jeu, media_temporaire):
    exif = Image.Exif()
    exif[0x010F] = 'Marque secrète'
    exif[0x0132] = '2020:01:01 00:00:00'
    contenu = _octets('JPEG', (2400, 1600), exif=exif)
    assert b'Marque' in contenu
    client.force_login(jeu['compte'])
    r = _post_modifier(client, jeu, _fichier(contenu, 'IMG_originale_privee.jpg'))
    assert r.status_code == 200
    jeu['membre'].refresh_from_db()
    nom = jeu['membre'].photo.name
    assert re.fullmatch(r'[0-9a-f]{32}\.jpg', nom), nom
    assert 'originale' not in nom
    brut = (media_temporaire / nom).read_bytes()
    assert b'Marque' not in brut and b'Exif' not in brut
    with Image.open(media_temporaire / nom) as image:
        assert max(image.size) <= 1200 and len(image.getexif()) == 0
    vignette = media_temporaire / nom_vignette(nom)
    assert vignette.exists()
    with Image.open(vignette) as v:
        assert max(v.size) <= 160


def test_F22_nom_original_malveillant_jamais_conserve(client, jeu, media_temporaire):
    client.force_login(jeu['compte'])
    _post_modifier(client, jeu, _fichier(_octets('PNG'), '../../etc/passwd<script>.png'))
    jeu['membre'].refresh_from_db()
    assert re.fullmatch(r'[0-9a-f]{32}\.png', jeu['membre'].photo.name)
    assert not any(('..' in n or '/' in n) for n in _fichiers_ecrits(media_temporaire))


def test_F22_extension_imposee_par_le_format_reel(client, jeu):
    client.force_login(jeu['compte'])
    _post_modifier(client, jeu, _fichier(_octets('PNG'), 'trompeur.jpg'))
    jeu['membre'].refresh_from_db()
    assert jeu['membre'].photo.name.endswith('.png')


# ---------------------------------------------------------------- mobapp

def _donnees_inscription(jeu, **extra):
    d = {'nom': 'Inscrit Mobile', 'genre': 'HOMME', 'qualite': 'PROPRIETAIRE', 'province': jeu['province'].id,
         'date_naissance': '1992-05-06', 'lieux_naissance': 'Kinshasa', 'telephone': '+243800000000',
         'password1': 'Mot-de-passe-9x', 'password2': 'Mot-de-passe-9x'}
    d.update(extra)
    return d


def test_F22_mobapp_inscription_avec_photo_valide_fonctionne_encore(client, jeu, media_temporaire):
    r = client.post(reverse('register'), _donnees_inscription(jeu, photo=_fichier(_octets('JPEG', (800, 600)), 'moi.jpg')))
    assert r.status_code == 302, r.content.decode()[:2000]
    membre = Membre.objects.get(nom='Inscrit Mobile')
    assert re.fullmatch(r'[0-9a-f]{32}\.jpg', membre.photo.name)
    assert (media_temporaire / nom_vignette(membre.photo.name)).exists()
    assert membre.idf.startswith('MBR')


def test_F22_mobapp_inscription_sans_photo(client, jeu):
    r = client.post(reverse('register'), _donnees_inscription(jeu))
    assert r.status_code == 302 and Membre.objects.filter(nom='Inscrit Mobile').exists()


@pytest.mark.parametrize('cle', ['svg', 'html', 'gif_reel', 'texte'])
def test_F22_mobapp_inscription_refuse_faux_fichier_sans_500(client, jeu, cle, media_temporaire):
    contenu, nom = REFUSES[cle]
    r = client.post(reverse('register'), _donnees_inscription(jeu, photo=_fichier(contenu, nom)))
    assert r.status_code == 200  # formulaire réaffiché avec l'erreur
    assert not Membre.objects.filter(nom='Inscrit Mobile').exists()
    assert _fichiers_ecrits(media_temporaire) == []


def test_F22_mobapp_inscription_bombe_sans_500(client, jeu, media_temporaire):
    r = client.post(reverse('register'),
                    _donnees_inscription(jeu, photo=_fichier(_octets('PNG', (20000, 20000), mode='1'), 'b.png')))
    assert r.status_code == 200 and not Membre.objects.filter(nom='Inscrit Mobile').exists()
    assert _fichiers_ecrits(media_temporaire) == []
