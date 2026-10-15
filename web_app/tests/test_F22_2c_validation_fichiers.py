"""Validation indépendante du sous-lot 2c (testeur) : /fichiers/… (matrice, en-têtes, contenus hostiles, chemins) et
commande deplacer_fichiers_prives. Données fictives uniquement."""
import hashlib
import io
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from PIL import Image

from compte.models import Compte
from coptapp.models import Membre
from tests.test_F21_matrice_routes import acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

PDF = b'%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n'


def _jpeg(taille=(300, 300)):
    t = io.BytesIO()
    Image.new('RGB', taille, (200, 30, 30)).save(t, 'JPEG')
    return t.getvalue()


@pytest.fixture
def dossiers(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / 'media'
    settings.PRIVATE_MEDIA_ROOT = tmp_path / 'prive'
    (tmp_path / 'media').mkdir()
    return settings.MEDIA_ROOT, settings.PRIVATE_MEDIA_ROOT


@pytest.fixture
def pieces(acteurs, dossiers):
    m, a = acteurs['membre'], acteurs['association']
    Membre.objects.filter(pk=m.pk).update(etat='actif')
    m.refresh_from_db()
    m.fiche_id = SimpleUploadedFile('identite-secrete.pdf', PDF)
    m.photo = SimpleUploadedFile('visage.jpg', _jpeg())
    m.save()
    a.capture_justice = SimpleUploadedFile('f92-secret.jpg', _jpeg())
    a.preuve_de_paiement = SimpleUploadedFile('paiement-secret.jpg', _jpeg())
    a.save()
    return acteurs


def _u(type_objet, id_, champ, vignette=False):
    u = reverse('fichier', kwargs={'type_objet': type_objet, 'id': id_, 'champ': champ})
    return u + '?vignette=1' if vignette else u


def _ressources(p):
    m, a = p['membre'].id, p['association'].id
    return {
        'photo': _u('membre', m, 'photo'), 'vignette': _u('membre', m, 'photo', True),
        'fiche_id': _u('membre', m, 'fiche_id'),
        'capture_justice': _u('association', a, 'capture_justice'),
        'preuve_de_paiement': _u('association', a, 'preuve_de_paiement'),
    }


def _statut(client, url):
    r = client.get(url)
    if r.streaming:
        r.close()
    return r.status_code


# profil -> statut attendu par ressource (photo, vignette, fiche_id, capture_justice, preuve_de_paiement)
# Jeu : membre entièrement validé, saisi par p1 ; association A = p1, p2, p3 ; p4 hors de l'association.
ATTENDU = {
    'su': (200, 200, 200, 200, 200),
    'p5': (200, 200, 200, 200, 200),
    'p1': (200, 200, 200, 200, 200),
    'p2': (200, 200, 200, 200, 200),
    'p3': (200, 200, 200, 200, 200),
    'p4': (200, 200, 403, 404, 404),  # lecture seule : photo oui, pièces non ; association hors compte : 404
    'nu': (404, 404, 404, 404, 404),
    'ed': (404, 404, 404, 404, 404),
}
CLES = ('photo', 'vignette', 'fiche_id', 'capture_justice', 'preuve_de_paiement')


@pytest.mark.parametrize('profil', sorted(ATTENDU))
def test_F22_2c_matrice_profils_par_ressource(client, pieces, profil):
    client.force_login(pieces['comptes'][profil])
    urls = _ressources(pieces)
    obtenu = tuple(_statut(client, urls[c]) for c in CLES)
    assert obtenu == ATTENDU[profil], (profil, dict(zip(CLES, obtenu)))


def test_F22_2c_matrice_anonyme_redirige_vers_la_connexion(client, pieces):
    for cle, url in _ressources(pieces).items():
        r = client.get(url)
        assert r.status_code == 302 and '/connexion/' in r['Location'], cle


def test_F22_2c_p4_dans_l_association_est_refuse_sur_les_pieces_d_association(client, pieces):
    pieces['association'].users.add(pieces['comptes']['p4'])
    client.force_login(pieces['comptes']['p4'])
    urls = _ressources(pieces)
    assert _statut(client, urls['capture_justice']) == 403 and _statut(client, urls['preuve_de_paiement']) == 403


def test_F22_2c_adresse_champ_url_meme_controle(client, pieces):
    """/fichiers/nom/<nom> (champ.url) applique les mêmes droits que la vue par identifiant."""
    m = pieces['membre']
    assert client.get(m.photo.url).status_code == 302
    client.force_login(pieces['comptes']['p4'])
    assert _statut(client, m.photo.url) == 200 and _statut(client, m.fiche_id.url) == 403
    client.force_login(pieces['comptes']['nu'])
    assert _statut(client, m.photo.url) == 404 and _statut(client, m.fiche_id.url) == 404


def test_F22_2c_en_tetes(client, pieces):
    client.force_login(pieces['comptes']['su'])
    cas = {'photo': 'image/jpeg', 'vignette': 'image/jpeg', 'fiche_id': 'application/pdf',
           'capture_justice': 'image/jpeg', 'preuve_de_paiement': 'image/jpeg'}
    for cle, url in _ressources(pieces).items():
        r = client.get(url)
        r.close()
        assert r['Content-Type'] == cas[cle], cle
        assert r['X-Content-Type-Options'] == 'nosniff', cle
        disp = r['Content-Disposition']
        assert disp.startswith('inline; filename="') and not any(s in disp for s in ('secret', 'visage', 'identite', 'f92')), (cle, disp)
        cc = r['Cache-Control']
        assert 'private' in cc, cle
        if cle in ('fiche_id', 'capture_justice', 'preuve_de_paiement'):
            assert 'no-store' in cc, (cle, cc)
        else:
            assert 'public' not in cc, (cle, cc)


def test_F22_2c_type_decide_par_le_contenu_pas_par_l_extension(client, pieces, dossiers):
    _, prive = dossiers
    m = pieces['membre']
    chemin = prive / m.fiche_id.name
    chemin.write_bytes(_jpeg())  # une image dans une « fiche_id » : type réel, jamais l'extension .pdf
    client.force_login(pieces['comptes']['su'])
    r = client.get(_u('membre', m.id, 'fiche_id'))
    r.close()
    assert r['Content-Type'] == 'image/jpeg' and r['Content-Disposition'].endswith('.jpg"')


@pytest.mark.parametrize('contenu', [
    b'<html><script>alert(1)</script></html>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
    b'GIF89a<script>x</script>',
    b'\x00\x01\x02 binaire inconnu',
    b'',
    b'<?php system($_GET[1]); ?>',
])
def test_F22_2c_contenu_hostile_renomme_jamais_servi(client, pieces, dossiers, contenu):
    _, prive = dossiers
    m = pieces['membre']
    for fichier in (m.fiche_id, m.photo):
        (prive / fichier.name).write_bytes(contenu)
    (prive / pieces['association'].capture_justice.name).write_bytes(contenu)
    client.force_login(pieces['comptes']['su'])
    for cle in ('photo', 'fiche_id', 'capture_justice'):
        assert _statut(client, _ressources(pieces)[cle]) == 404, cle
    # la vignette (absente ou hostile) ne se replie jamais sur un contenu non reconnu
    (prive / Path(m.photo.name).with_name(Path(m.photo.name).stem + '_vignette.jpg')).write_bytes(contenu)
    assert _statut(client, _ressources(pieces)['vignette']) == 404


def test_F22_2c_televersement_hostile_refuse_a_l_enregistrement(pieces):
    m = pieces['membre']
    for nom in ('a.jpg', 'a.png', 'a.pdf'):
        m.photo = SimpleUploadedFile(nom, b'<html><script>alert(1)</script></html>')
        with pytest.raises(ValidationError):
            m.save()
    m.refresh_from_db()
    m.fiche_id = SimpleUploadedFile('a.pdf', b'<html>pas un pdf</html>')
    with pytest.raises(ValidationError):
        m.save()


@pytest.mark.parametrize('chemin', [
    '/fichiers/nom/../../../etc/passwd', '/fichiers/nom/..%2f..%2fsecret.pdf', '/fichiers/nom/%2e%2e/%2e%2e/secret.pdf',
    '/fichiers/nom/....//....//secret.pdf', '/fichiers/nom//etc/passwd', '/fichiers/nom/..\\..\\secret.pdf',
    '/fichiers/nom/x.jpg%00.pdf',
])
def test_F22_2c_chemin_avec_remontee_refuse(client, pieces, dossiers, chemin):
    media, prive = dossiers
    (prive.parent / 'secret.pdf').write_bytes(PDF)
    client.force_login(pieces['comptes']['su'])
    r = client.get(chemin)
    if r.streaming:
        r.close()
    assert r.status_code in (400, 404)
    assert b'%PDF' not in (b''.join(r.streaming_content) if r.streaming else r.content)


def test_F22_2c_nom_en_base_avec_remontee_ne_sert_pas_un_fichier_hors_dossier(client, pieces, dossiers):
    _, prive = dossiers
    (prive.parent / 'secret.pdf').write_bytes(PDF)
    Membre.objects.filter(pk=pieces['membre'].pk).update(fiche_id='../secret.pdf')
    client.force_login(pieces['comptes']['su'])
    r = client.get(_u('membre', pieces['membre'].id, 'fiche_id'))
    if r.streaming:
        r.close()
    assert r.status_code in (400, 404) and not r.streaming
    r = client.get('/fichiers/nom/../secret.pdf')
    assert r.status_code in (400, 404)


def test_F22_2c_champs_et_types_non_exposes(client, pieces):
    client.force_login(pieces['comptes']['su'])
    m = pieces['membre'].id
    for chemin in (_u('membre', m, 'password'), _u('membre', m, 'nom'), _u('membre', m, 'capture_justice'),
                   _u('association', pieces['association'].id, 'photo'), _u('moto', m, 'photo'),
                   _u('membre', m, '..'), _u('membre', m, 'photo.jpg')):
        assert client.get(chemin).status_code == 404, chemin
    for methode in ('post', 'put', 'delete'):
        assert getattr(client, methode)(_u('membre', m, 'photo')).status_code == 405


def test_F22_2c_aucun_fichier_prive_sous_media(client, pieces, dossiers, settings):
    media, prive = dossiers
    assert settings.MEDIA_URL == '/media/'
    assert Path(settings.PRIVATE_MEDIA_ROOT).resolve() != Path(settings.MEDIA_ROOT).resolve()
    assert Path(settings.MEDIA_ROOT).resolve() not in Path(settings.PRIVATE_MEDIA_ROOT).resolve().parents
    m, a = pieces['membre'], pieces['association']
    noms = [m.fiche_id.name, m.photo.name, a.capture_justice.name, a.preuve_de_paiement.name]
    for nom in noms:
        assert (prive / nom).exists() and not (media / nom).exists()
    client.force_login(pieces['comptes']['su'])
    for nom in noms + [m.photo.name.replace('.jpg', '_vignette.jpg')]:
        assert client.get(settings.MEDIA_URL + nom.lstrip('./')).status_code == 404, nom


# ---------------------------------------------------------------- commande deplacer_fichiers_prives

def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@pytest.fixture
def anciens(pieces, dossiers):
    media, prive = dossiers
    (media / 'fiche_id').mkdir()
    (media / 'F92').mkdir()
    (media / 'fiche_id' / 'a.pdf').write_bytes(PDF)
    (media / 'p.jpg').write_bytes(_jpeg())
    (media / 'p_vignette.jpg').write_bytes(_jpeg((40, 40)))
    (media / 'F92' / 'c.jpg').write_bytes(_jpeg((80, 80)))
    # état « ancien » : les nouveaux fichiers de la fixture sont retirés, les noms pointent vers MEDIA_ROOT
    import shutil
    shutil.rmtree(prive, ignore_errors=True)
    Membre.objects.filter(pk=pieces['membre'].pk).update(fiche_id='fiche_id/a.pdf', photo='p.jpg')
    type(pieces['association']).objects.filter(pk=pieces['association'].pk).update(
        capture_justice='F92/c.jpg', preuve_de_paiement='')
    return media, prive


def _arbre(racine):
    return {p.relative_to(racine).as_posix(): _sha(p) for p in Path(racine).rglob('*') if p.is_file()} if Path(racine).exists() else {}


def test_F22_2c_commande_dry_run_ne_modifie_rien(anciens, capsys):
    media, prive = anciens
    avant = (_arbre(media), _arbre(prive), prive.exists())
    call_command('deplacer_fichiers_prives', '--dry-run')
    assert (_arbre(media), _arbre(prive), prive.exists()) == avant
    assert 'Simulation' in capsys.readouterr().out


def test_F22_2c_commande_reel_deplace_a_l_identique_et_se_rejoue(anciens):
    media, prive = anciens
    avant = _arbre(media)
    call_command('deplacer_fichiers_prives')
    assert _arbre(media) == {}
    assert _arbre(prive) == avant  # mêmes chemins relatifs, mêmes SHA-256
    call_command('deplacer_fichiers_prives')  # deuxième fois : sans dommage
    call_command('deplacer_fichiers_prives', '--dry-run')
    assert _arbre(prive) == avant and _arbre(media) == {}


def test_F22_2c_commande_conflit_code_d_erreur_et_aucune_suppression(anciens, capsys):
    media, prive = anciens
    (prive / 'fiche_id').mkdir(parents=True)
    (prive / 'fiche_id' / 'a.pdf').write_bytes(b'%PDF-1.4 autre\n%%EOF\n')
    avant_media, autre = _arbre(media), _sha(prive / 'fiche_id' / 'a.pdf')
    with pytest.raises(CommandError):
        call_command('deplacer_fichiers_prives')
    assert 'fiche_id/a.pdf' in _arbre(media) and _sha(media / 'fiche_id' / 'a.pdf') == avant_media['fiche_id/a.pdf']
    assert _sha(prive / 'fiche_id' / 'a.pdf') == autre  # la destination n'est jamais écrasée
    # les autres fichiers n'ont pas été perdus : soit encore en source, soit en destination identique
    for rel, empreinte in avant_media.items():
        assert (_sha(media / rel) if (media / rel).exists() else _sha(prive / rel)) in (empreinte, autre)


def test_F22_2c_commande_nom_suspect_jamais_touche(anciens):
    media, prive = anciens
    dehors = media.parent / 'dehors.pdf'
    dehors.write_bytes(PDF)
    Membre.objects.filter(pk=anciens and Membre.objects.first().pk).update(fiche_id='../dehors.pdf')
    with pytest.raises(CommandError):
        call_command('deplacer_fichiers_prives')
    assert dehors.exists() and _sha(dehors) == hashlib.sha256(PDF).hexdigest()
