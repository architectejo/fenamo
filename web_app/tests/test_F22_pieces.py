"""F-22 / E2 : pièce jointe Membre.fiche_id (PDF, JPEG, PNG), nom aléatoire ; formulaires sans mot de passe ni identifiant."""
import io
import re

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from coptapp.forms import MembreFenamoForm, MembreForm
from coptapp.models import Membre
from coptapp.validators import erreur_piece, valider_piece
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

PDF = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
HTML = b'<html><script>alert(1)</script></html>'


@pytest.fixture(autouse=True)
def media_temporaire(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def _image(format_):
    tampon = io.BytesIO()
    Image.new('RGB', (20, 20), (9, 9, 9)).save(tampon, format_)
    return tampon.getvalue()


@pytest.mark.parametrize('contenu', [PDF, _image('JPEG'), _image('PNG')])
def test_F22_pieces_acceptees(contenu):
    valider_piece(SimpleUploadedFile('scan.bin', contenu))


@pytest.mark.parametrize('contenu, nom', [(HTML, 'carte.pdf'), (SVG, 'carte.jpg'), (HTML, 'carte.png'),
                                          (_image('GIF'), 'carte.jpg'), (_image('WEBP'), 'carte.jpg'), (b'', 'vide.pdf')])
def test_F22_pieces_refusees(contenu, nom):
    fichier = SimpleUploadedFile(nom, contenu)
    with pytest.raises(ValidationError):
        valider_piece(fichier)
    assert erreur_piece(fichier)


def test_F22_piece_trop_lourde(settings):
    settings.UPLOAD_PIECE_MAX_MO = 0.0001
    assert 'lourd' in erreur_piece(SimpleUploadedFile('a.pdf', PDF + b'0' * 500))


def test_F22_piece_enregistree_sous_nom_aleatoire_et_extension_reelle(jeu):
    membre = jeu['membre']
    membre.fiche_id = SimpleUploadedFile('Mon identite.jpg', PDF)  # un PDF déguisé en .jpg reste un PDF
    membre.save()
    assert re.fullmatch(r'fiche_id/[0-9a-f]{32}\.pdf', membre.fiche_id.name), membre.fiche_id.name
    assert membre.fiche_id.read().startswith(b'%PDF')


def test_F22_piece_html_deguisee_refusee_a_l_enregistrement(jeu):
    membre = jeu['membre']
    membre.fiche_id = SimpleUploadedFile('x.pdf', HTML)
    with pytest.raises(ValidationError):
        membre.save()
    membre.refresh_from_db()
    assert not membre.fiche_id


def test_F22_piece_validateur_sur_le_champ(jeu):
    membre = jeu['membre']
    membre.fiche_id = SimpleUploadedFile('x.pdf', SVG)
    with pytest.raises(ValidationError) as erreur:
        membre.full_clean(exclude=['password'])
    assert 'fiche_id' in erreur.value.message_dict


def test_E2_formulaires_sans_mot_de_passe_ni_identifiant():
    for formulaire in (MembreForm, MembreFenamoForm):
        assert 'password' not in formulaire.base_fields and 'idf' not in formulaire.base_fields


def test_E2_mobapp_ne_depend_pas_des_formulaires_coptapp():
    from mobapp.forms import MembreFormRegister
    assert 'password' not in MembreFormRegister.base_fields and 'idf' not in MembreFormRegister.base_fields
