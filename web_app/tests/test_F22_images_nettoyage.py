"""Images : commentaire JPEG supprimé, MPO accepté, 25 Mpx, suppression des anciens fichiers après commit (F-22)."""
import io
import re

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from coptapp.models import Membre
from coptapp.services.membres import normaliser_filtres
from coptapp.validators import erreur_image, nom_vignette
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


@pytest.fixture(autouse=True)
def media_temporaire(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.PRIVATE_MEDIA_ROOT = tmp_path  # même dossier : les tests lisent les fichiers à un seul endroit
    return tmp_path


def _jpeg(commentaire=b'', taille=(40, 40)):
    tampon = io.BytesIO()
    Image.new('RGB', taille, (5, 5, 5)).save(tampon, 'JPEG', comment=commentaire) if commentaire else Image.new('RGB', taille).save(tampon, 'JPEG')
    return tampon.getvalue()


def test_F22_polyglotte_commentaire_jpeg_html_supprime(jeu):
    piege = b'<script>alert(1)</script>'
    brut = _jpeg(piege)
    assert piege in brut
    jeu['membre'].photo = SimpleUploadedFile('p.jpg', brut)
    jeu['membre'].save()
    assert piege not in jeu['membre'].photo.read() and b'<script' not in open(jeu['membre'].photo.path, 'rb').read()


def test_F22_png_sans_texte(jeu):
    from PIL.PngImagePlugin import PngInfo
    info = PngInfo()
    info.add_text('x', '<script>alert(1)</script>')
    tampon = io.BytesIO()
    Image.new('RGB', (10, 10)).save(tampon, 'PNG', pnginfo=info)
    jeu['membre'].photo = SimpleUploadedFile('p.png', tampon.getvalue())
    jeu['membre'].save()
    assert b'<script' not in open(jeu['membre'].photo.path, 'rb').read()


def test_F22_pixels_max_25_millions():
    tampon = io.BytesIO()
    Image.new('1', (6000, 5000)).save(tampon, 'PNG')  # 30 Mpx, très compressé
    assert 'pixels' in erreur_image(SimpleUploadedFile('g.png', tampon.getvalue()))


def test_F22_mpo_accepte_et_reencode_en_jpeg(jeu):
    tampon = io.BytesIO()
    image = Image.new('RGB', (30, 30), (1, 2, 3))
    image.save(tampon, 'MPO', save_all=True, append_images=[Image.new('RGB', (30, 30))])
    fichier = SimpleUploadedFile('p.jpg', tampon.getvalue())
    assert Image.open(io.BytesIO(tampon.getvalue())).format == 'MPO'
    assert erreur_image(fichier) is None
    jeu['membre'].photo = fichier
    jeu['membre'].save()
    assert re.fullmatch(r'[0-9a-f]{32}\.jpg', jeu['membre'].photo.name)


def test_F22_remplacement_supprime_ancien_fichier_et_vignette_apres_commit(jeu, media_temporaire, django_capture_on_commit_callbacks):
    membre = jeu['membre']
    membre.photo = SimpleUploadedFile('a.jpg', _jpeg())
    membre.save()
    ancien = membre.photo.name
    assert (media_temporaire / ancien).exists() and (media_temporaire / nom_vignette(ancien)).exists()
    with django_capture_on_commit_callbacks(execute=False) as rappels:
        membre.photo = SimpleUploadedFile('b.jpg', _jpeg())
        membre.save()
    assert (media_temporaire / ancien).exists()  # rien n'est supprimé avant le commit
    for rappel in rappels:
        rappel()
    assert not (media_temporaire / ancien).exists() and not (media_temporaire / nom_vignette(ancien)).exists()
    assert (media_temporaire / membre.photo.name).exists()


def test_F22_suppression_de_la_ligne_supprime_les_fichiers(jeu, media_temporaire, django_capture_on_commit_callbacks):
    membre = Membre.objects.create(nom='Temp', photo=SimpleUploadedFile('a.jpg', _jpeg()))
    nom = membre.photo.name
    with django_capture_on_commit_callbacks(execute=True):
        membre.delete()
    assert not (media_temporaire / nom).exists() and not (media_temporaire / nom_vignette(nom)).exists()


def test_F22_fichier_partage_non_supprime(jeu, media_temporaire, django_capture_on_commit_callbacks):
    membre = Membre.objects.create(nom='A', photo=SimpleUploadedFile('a.jpg', _jpeg()))
    Membre.objects.create(nom='B', photo=membre.photo.name)  # même fichier (donnée héritée)
    with django_capture_on_commit_callbacks(execute=True):
        membre.delete()
    assert (media_temporaire / Membre.objects.get(nom='B').photo.name).exists()


def test_F22_article_sans_nouveau_fichier_garde_son_image(client, jeu, media_temporaire):
    article = jeu['article']
    article.image = SimpleUploadedFile('a.jpg', _jpeg())
    article.save()
    nom = article.image.name
    client.force_login(jeu['compte'])
    from django.urls import reverse
    client.post(reverse('article', args=[article.id]), {'titre': 'Titre 2', 'description': 'd'})
    article.refresh_from_db()
    assert article.titre == 'Titre 2' and article.image.name == nom and (media_temporaire / nom).exists()
    r = client.post(reverse('article', args=[article.id]),
                    {'titre': 'Titre 3', 'description': 'd', 'image': SimpleUploadedFile('x.jpg', b'<html>')})
    article.refresh_from_db()
    assert r.status_code == 400 and article.image.name == nom and (media_temporaire / nom).exists()


def test_F28_filtre_entier_hors_plage_ignore():
    assert normaliser_filtres({'antenne': '9' * 40, 'association': '9' * 40}) ['antenne'] == ''
    assert normaliser_filtres({'association': str(2**63)})['association'] == ''
    assert normaliser_filtres({'association': str(2**63 - 1)})['association'] == 2**63 - 1
