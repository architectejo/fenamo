"""§ 9.4 / F-22 : pièces et photos privées hors de la racine web, servies par une vue contrôlée ; commande de déplacement."""
import io
import shutil

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.urls import reverse
from PIL import Image

from compte.models import Compte, JournalAction
from coptapp.models import AssociationMembre, Membre
from coptapp.services.fichiers_prives import deplacer_fichiers_prives, hachage
from coptapp.validators import nom_vignette
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

PDF = b'%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n'


def _jpeg(taille=(300, 300)):
    tampon = io.BytesIO()
    Image.new('RGB', taille, (10, 80, 160)).save(tampon, 'JPEG')
    return tampon.getvalue()


@pytest.fixture
def dossiers(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / 'media'
    settings.PRIVATE_MEDIA_ROOT = tmp_path / 'prive'
    return settings.MEDIA_ROOT, settings.PRIVATE_MEDIA_ROOT


@pytest.fixture
def pieces(jeu, dossiers):
    membre = jeu['membre']
    membre.fiche_id = SimpleUploadedFile('identite.pdf', PDF)
    membre.photo = SimpleUploadedFile('moi.jpg', _jpeg())
    membre.save()
    association = jeu['association']
    association.capture_justice = SimpleUploadedFile('f92.jpg', _jpeg())
    association.preuve_de_paiement = SimpleUploadedFile('paiement.jpg', _jpeg())
    association.save()
    return jeu


def _url(type_objet, id, champ):
    return reverse('fichier', kwargs={'type_objet': type_objet, 'id': id, 'champ': champ})


# ---------------------------------------------------------------- stockage privé

def test_F22_fichiers_prives_ecrits_hors_de_media_root(pieces, dossiers):
    media, prive = dossiers
    for fichier in (pieces['membre'].fiche_id, pieces['membre'].photo, pieces['association'].capture_justice,
                    pieces['association'].preuve_de_paiement):
        assert (prive / fichier.name).exists() and not (media / fichier.name).exists()
    assert (prive / nom_vignette(pieces['membre'].photo.name)).exists()


def test_F22_aucune_piece_servie_sous_media(client, pieces, dossiers):
    client.force_login(pieces['compte'])
    for fichier in (pieces['membre'].fiche_id, pieces['membre'].photo, pieces['association'].capture_justice,
                    pieces['association'].preuve_de_paiement):
        assert client.get('/media/' + fichier.name).status_code == 404
    assert client.get('/media/F92/introuvable.jpg').status_code == 404


def test_F22_url_du_champ_pointe_vers_la_vue_controlee(client, pieces):
    adresse = pieces['membre'].photo.url
    assert adresse.startswith('/fichiers/nom/') and '/media/' not in adresse
    assert client.get(adresse).status_code == 302  # anonyme : connexion
    client.force_login(pieces['compte'])
    assert client.get(adresse).status_code == 200


# ---------------------------------------------------------------- vue contrôlée

def test_F22_vue_en_tetes_et_type_reel(client, pieces):
    client.force_login(pieces['compte'])
    r = client.get(_url('membre', pieces['membre'].id, 'fiche_id'))
    assert r.status_code == 200 and r['Content-Type'] == 'application/pdf'
    assert r['X-Content-Type-Options'] == 'nosniff' and 'no-store' in r['Cache-Control'] and 'private' in r['Cache-Control']
    assert r['Content-Disposition'] == 'inline; filename="fiche_id.pdf"'
    assert b''.join(r.streaming_content).startswith(b'%PDF')
    r = client.get(_url('membre', pieces['membre'].id, 'photo'))
    assert r['Content-Type'] == 'image/jpeg' and r['Content-Disposition'] == 'inline; filename="photo.jpg"'
    assert 'private' in r['Cache-Control']  # (un middleware ajoute no-store à toute page connectée)


def test_F22_vue_vignette(client, pieces):
    client.force_login(pieces['compte'])
    r = client.get(_url('membre', pieces['membre'].id, 'photo'), {'vignette': '1'})
    corps = b''.join(r.streaming_content)
    assert r.status_code == 200 and Image.open(io.BytesIO(corps)).width <= 160


def test_F22_vue_contenu_modifie_en_html_jamais_servi(client, pieces, dossiers):
    _, prive = dossiers
    (prive / pieces['membre'].fiche_id.name).write_bytes(b'<html><script>alert(1)</script></html>')
    client.force_login(pieces['compte'])
    assert client.get(_url('membre', pieces['membre'].id, 'fiche_id')).status_code == 404


def test_F22_vue_pieces_d_association(client, pieces):
    client.force_login(pieces['compte'])
    for champ in ('capture_justice', 'preuve_de_paiement'):
        r = client.get(_url('association', pieces['association'].id, champ))
        assert r.status_code == 200 and r['Content-Type'] == 'image/jpeg' and r['X-Content-Type-Options'] == 'nosniff'


def test_F22_vue_perimetre_droits_et_champs_inconnus(client, pieces):
    membre, association = pieces['membre'], pieces['association']
    assert Client().get(_url('membre', membre.id, 'photo')).status_code == 302
    sans = Compte.objects.create_user('sans', password='x')
    client.force_login(sans)
    assert client.get(_url('membre', membre.id, 'photo')).status_code == 404  # hors périmètre
    assert client.get(_url('association', association.id, 'capture_justice')).status_code == 404
    visiteur = Compte.objects.create_user('visiteur', password='x', privilege4=True)
    Membre.objects.filter(pk=membre.pk).update(is_validate2=True, is_validate3=True)
    association.users.add(visiteur)
    client.force_login(visiteur)
    assert client.get(_url('membre', membre.id, 'photo')).status_code == 200  # la photo : périmètre suffit
    assert client.get(_url('membre', membre.id, 'fiche_id')).status_code == 403  # pas la pièce d'identité
    assert client.get(_url('association', association.id, 'preuve_de_paiement')).status_code == 403
    client.force_login(pieces['compte'])
    for chemin in (_url('membre', membre.id, 'password'), _url('membre', membre.id, 'nom'),
                   _url('inconnu', membre.id, 'photo'), _url('membre', 99999, 'photo')):
        assert client.get(chemin).status_code == 404, chemin
    assert client.get('/fichiers/nom/inexistant.jpg').status_code == 404
    assert client.post(_url('membre', membre.id, 'photo')).status_code == 405


def test_F22_consultation_d_une_piece_journalisee_pas_celle_d_une_photo(client, pieces):
    client.force_login(pieces['compte'])
    client.get(_url('membre', pieces['membre'].id, 'photo'))
    assert not JournalAction.objects.filter(action=JournalAction.Action.CONSULTATION_PIECE).exists()
    client.get(_url('membre', pieces['membre'].id, 'fiche_id'))
    client.get(_url('association', pieces['association'].id, 'capture_justice'))
    lignes = JournalAction.objects.filter(action=JournalAction.Action.CONSULTATION_PIECE)
    assert lignes.count() == 2 and lignes.filter(auteur=pieces['compte'], objet_libelle='fiche_id').exists()


def test_F22_balise_url_fichier(pieces):
    from django.template import Context, Template
    gabarit = Template('{% load fichiers %}{% url_fichier m "photo" %}|{% url_fichier m "photo" vignette=True %}|{% url_fichier m "fiche_id" %}|{% url_fichier v "photo" %}')
    sortie = gabarit.render(Context({'m': pieces['membre'], 'v': Membre()}))
    id_ = pieces['membre'].id
    assert sortie == f'/fichiers/membre/{id_}/photo/|/fichiers/membre/{id_}/photo/?vignette=1|/fichiers/membre/{id_}/fiche_id/|'


# ---------------------------------------------------------------- commande de déplacement

@pytest.fixture
def anciens(jeu, dossiers):
    """Fichiers déjà enregistrés l'ancienne manière : dans MEDIA_ROOT, noms en base."""
    media, prive = dossiers
    (media / 'fiche_id').mkdir(parents=True)
    (media / 'fiche_id' / 'a.pdf').write_bytes(PDF)
    (media / 'p.jpg').write_bytes(_jpeg())
    (media / 'p_vignette.jpg').write_bytes(_jpeg((50, 50)))
    Membre.objects.filter(pk=jeu['membre'].pk).update(fiche_id='fiche_id/a.pdf', photo='p.jpg')
    return media, prive


def test_F22_commande_dry_run_ne_touche_a_rien(anciens, capsys):
    media, prive = anciens
    call_command('deplacer_fichiers_prives', '--dry-run')
    assert (media / 'p.jpg').exists() and not prive.exists()
    assert 'Simulation' in capsys.readouterr().out


def test_F22_commande_deplace_verifie_les_hachages_et_se_rejoue(anciens):
    media, prive = anciens
    empreinte = hachage(media / 'fiche_id' / 'a.pdf')
    call_command('deplacer_fichiers_prives')
    assert not (media / 'fiche_id' / 'a.pdf').exists() and hachage(prive / 'fiche_id' / 'a.pdf') == empreinte
    assert (prive / 'p.jpg').exists() and (prive / 'p_vignette.jpg').exists() and not (media / 'p.jpg').exists()
    rapport = deplacer_fichiers_prives()  # rejoué : rien à faire, rien perdu
    assert rapport['deplaces'] == [] and rapport['conflits'] == []
    call_command('deplacer_fichiers_prives')


def test_F22_commande_destination_differente_conflit_source_conservee(anciens):
    media, prive = anciens
    (prive / 'fiche_id').mkdir(parents=True)
    (prive / 'fiche_id' / 'a.pdf').write_bytes(b'%PDF-1.4 autre contenu\n%%EOF\n')
    with pytest.raises(CommandError):
        call_command('deplacer_fichiers_prives')
    assert (media / 'fiche_id' / 'a.pdf').read_bytes() == PDF  # la source n'est jamais supprimée sans copie vérifiée


def test_F22_commande_destination_identique_supprime_la_source(anciens):
    media, prive = anciens
    (prive / 'fiche_id').mkdir(parents=True)
    shutil.copy2(media / 'fiche_id' / 'a.pdf', prive / 'fiche_id' / 'a.pdf')
    call_command('deplacer_fichiers_prives')
    assert not (media / 'fiche_id' / 'a.pdf').exists()
