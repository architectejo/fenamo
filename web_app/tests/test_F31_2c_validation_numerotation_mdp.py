"""Validation indépendante 2c : numérotation F-31 (successifs, verrou, concurrence simulée, coordination inconnue),
mot de passe mobile défini par un agent (droits, lecture unique, journal, cookie, cache) et gabarits sans /media/."""
import re
import threading
from datetime import date
from html import unescape
from pathlib import Path

import pytest
from django.contrib.auth.hashers import check_password
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.urls import reverse

from compte.models import JournalAction
from compte.services.mobile import definir_mot_de_passe_membre, empreinte_session
from coptapp.models import Membre, Moto, Province
from coptapp.services.engins import CoordinationInconnue, enregistrer_engin
from tests.test_F21_matrice_routes import acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

DONNEES = {'num_plaque': 'P', 'num_moteur': 'M1', 'num_chassie': 'C1', 'marque': 'X', 'couleur': 'ROUGE'}


def _d(i):
    return {**DONNEES, 'num_moteur': f'M{i}', 'num_chassie': f'C{i}'}


# ---------------------------------------------------------------- F-31 numérotation

def test_F31_2c_deux_enregistrements_successifs_numeros_distincts(jeu):
    a = enregistrer_engin(jeu['membre'], jeu['compte'], _d(1))
    b = enregistrer_engin(jeu['membre'], jeu['compte'], _d(2))
    assert (a.numero, b.numero) == ('002PF', '003PF') and a.numero != b.numero
    assert a.province_id == b.province_id == jeu['province'].id


def test_F31_2c_deux_enregistrements_via_mob_numeros_distincts(client, jeu):
    from django.contrib.auth.hashers import make_password
    m = Membre.objects.create(nom='Mob', idf='MBR0000042', password=make_password('x'), province=jeu['province'])
    s = client.session
    s['mob_membre_id'] = m.id
    s['mob_empreinte'] = empreinte_session(m)
    s.save()
    url = reverse('session', kwargs={'id': m.id})
    for i in (1, 2):
        client.post(url, {'num_plaque': 'P', 'num_moteur': f'M{i}', 'num_chassie': f'C{i}', 'marque': 'X', 'couleur': 'ROUGE'})
    numeros = list(Moto.objects.filter(proprietaire=m).order_by('id').values_list('numero', flat=True))
    assert numeros == ['002PF', '003PF']


def test_F31_2c_le_verrou_de_la_coordination_est_pris_dans_la_transaction(jeu, monkeypatch):
    """Simulation : on enregistre chaque appel à select_for_update et l'état transactionnel à ce moment."""
    from django.db.models.query import QuerySet
    appels = []
    original = QuerySet.select_for_update

    def espion(self, *a, **k):
        appels.append((self.model.__name__, connection.in_atomic_block))
        return original(self, *a, **k)

    monkeypatch.setattr(QuerySet, 'select_for_update', espion)
    enregistrer_engin(jeu['membre'], jeu['compte'], _d(1))
    assert ('Province', True) in appels


def test_F31_2c_numero_calcule_apres_le_verrou_pas_avant(jeu, monkeypatch):
    """Si un autre enregistrement s'intercale entre la lecture initiale et le verrou, le numéro tient compte de lui :
    numero_suivant n'est évalué qu'après l'acquisition du verrou."""
    import coptapp.services.engins as moteur
    ordre = []
    reel = moteur.numero_suivant

    def suivant(province):
        ordre.append('calcul')
        return reel(province)

    from django.db.models.query import QuerySet
    original = QuerySet.select_for_update

    def verrou(self, *a, **k):
        ordre.append('verrou')
        return original(self, *a, **k)

    monkeypatch.setattr(moteur, 'numero_suivant', suivant)
    monkeypatch.setattr(QuerySet, 'select_for_update', verrou)
    moteur.enregistrer_engin(jeu['membre'], jeu['compte'], _d(1))
    assert ordre.index('verrou') < ordre.index('calcul')


@pytest.mark.django_db(transaction=True)
def test_F31_2c_concurrence_deux_fils_jamais_deux_fois_le_meme_numero(jeu):
    """Deux fils enregistrent en même temps. SQLite n'a pas de verrou de ligne : les écritures se sérialisent (ou
    échouent proprement) ; dans tous les cas AUCUN doublon ne doit exister. (La garantie réelle, sous MySQL, est
    select_for_update : voir test du verrou ci-dessus ; il n'existe PAS de contrainte d'unicité en base.)"""
    from django.db import OperationalError
    resultats, erreurs = [], []
    barriere = threading.Barrier(4)
    membre_id, province_id = jeu['membre'].id, jeu['province'].id

    def travail(i):
        from django import db
        try:
            m = Membre.objects.get(pk=membre_id)
            barriere.wait(timeout=10)
            resultats.append(enregistrer_engin(m, None, _d(i)).numero)
        except OperationalError as e:  # base verrouillée : refus propre, pas de doublon
            erreurs.append(str(e))
        finally:
            db.connections.close_all()

    fils = [threading.Thread(target=travail, args=(i,)) for i in range(10, 14)]
    for f in fils:
        f.start()
    for f in fils:
        f.join(timeout=60)
    en_base = list(Moto.objects.filter(province_id=province_id).values_list('numero', flat=True))
    assert len(en_base) == len(set(en_base)), en_base
    assert len(resultats) + len(erreurs) == 4
    if not resultats:
        pytest.skip("SQLite refuse l'écriture concurrente : le test ne prouve rien hors MySQL")


def test_F31_2c_coordination_inconnue_ou_sans_code(jeu):
    sans = Membre.objects.create(nom='Sans coordination')
    with pytest.raises(CoordinationInconnue):
        enregistrer_engin(sans, jeu['compte'], _d(1))
    sans_code = Province.objects.create(nom='Sans code', sigle=None)
    m = Membre.objects.create(nom='Sans code', province=sans_code)
    with pytest.raises(CoordinationInconnue):
        enregistrer_engin(m, jeu['compte'], _d(1))
    vide = Province.objects.create(nom='Code vide', sigle='')
    with pytest.raises(CoordinationInconnue):
        enregistrer_engin(Membre.objects.create(nom='Code vide', province=vide), jeu['compte'], _d(1))
    assert Moto.objects.count() == 1  # seul l'engin du jeu


def test_F31_2c_mob_coordination_inconnue_message_et_rien_cree(client, jeu):
    from django.contrib.auth.hashers import make_password
    m = Membre.objects.create(nom='Orphelin', idf='MBR0000077', password=make_password('x'))
    s = client.session
    s['mob_membre_id'] = m.id
    s['mob_empreinte'] = empreinte_session(m)
    s.save()
    avant = Moto.objects.count()
    r = client.post(reverse('session', kwargs={'id': m.id}), {**_d(1)})
    assert r.status_code == 200 and 'coordination provinciale est inconnue' in r.content.decode()
    assert Moto.objects.count() == avant


# ---------------------------------------------------------------- mot de passe mobile défini par un agent

@pytest.fixture
def fiche(acteurs):
    Membre.objects.filter(pk=acteurs['membre'].pk).update(idf='MBR0000009', is_validate1=True, is_validate2=True,
                                                          is_validate3=True)
    acteurs['membre'].refresh_from_db()
    return acteurs


def _url_mdp(m):
    return reverse('mot-de-passe-mobile', kwargs={'id': m.id})


def _mdp_affiche(corps):
    """Le mot de passe affiché une fois, lu dans l'attribut data-mdp de l'encart (pas dans un message)."""
    m = re.search(r'data-mdp="([^"]+)"', unescape(corps))
    return m.group(1) if m else None


@pytest.mark.parametrize('profil, statut', [
    ('su', 200), ('p5', 200), ('p1', 200), ('p2', 200), ('p3', 200),
    ('p4', 403),   # voit le membre (validé) mais en lecture seule : refus de droit
    ('nu', 404), ('ed', 404),  # hors périmètre
])
def test_F20_2c_mdp_mobile_droits_par_profil(client, fiche, profil, statut):
    client.force_login(fiche['comptes'][profil])
    r = client.post(_url_mdp(fiche['membre']))
    assert r.status_code == statut, profil
    fiche['membre'].refresh_from_db()
    assert bool(fiche['membre'].password) == (statut == 200)


def test_F20_2c_mdp_mobile_anonyme_et_get(client, fiche):
    assert client.post(_url_mdp(fiche['membre'])).status_code == 302
    assert not Membre.objects.get(pk=fiche['membre'].pk).password
    client.force_login(fiche['comptes']['su'])
    assert client.get(_url_mdp(fiche['membre'])).status_code == 405
    assert not Membre.objects.get(pk=fiche['membre'].pk).password


def test_F20_2c_mdp_mobile_csrf_exige(fiche):
    from django.test import Client
    c = Client(enforce_csrf_checks=True)
    c.force_login(fiche['comptes']['su'])
    assert c.post(_url_mdp(fiche['membre'])).status_code == 403
    assert not Membre.objects.get(pk=fiche['membre'].pk).password


def test_F20_2c_mdp_service_droits(fiche):
    m = fiche['membre']
    for profil in ('p4', 'nu', 'ed'):
        with pytest.raises(PermissionDenied):
            definir_mot_de_passe_membre(fiche['comptes'][profil], m)
    assert definir_mot_de_passe_membre(fiche['comptes']['su'], m)


def test_F20_2c_mdp_affiche_dans_la_reponse_seule_hache_absent_du_reste(client, fiche, caplog):
    m = fiche['membre']
    client.force_login(fiche['comptes']['p1'])
    with caplog.at_level('DEBUG'):
        r = client.post(_url_mdp(m))
    assert r.status_code == 200 and 'Location' not in r  # réponse directe, aucune redirection
    clair = _mdp_affiche(r.content.decode())
    assert clair and len(clair) == 8 and r.context['mot_de_passe'] == clair
    cookies = ' '.join(c.value for c in r.cookies.values())
    m.refresh_from_db()
    assert m.password != clair and check_password(clair, m.password)
    # lecture unique : ni la fiche, ni le tableau de bord, ni les messages ne le redonnent
    assert clair not in client.get(reverse('membre-view', kwargs={'id': m.id})).content.decode()
    assert clair not in client.get(reverse('tableau-bord')).content.decode()
    for ligne in JournalAction.objects.all():
        assert clair not in ' '.join(str(getattr(ligne, f.name)) for f in ligne._meta.fields)
    assert clair not in cookies and all(clair not in c.value for c in client.cookies.values())
    assert clair not in caplog.text
    assert clair not in str(client.session.items())  # jamais dans la session (donc jamais dans les messages)


def test_F20_2c_mdp_fragment_htmx_et_page_complete(client, fiche):
    client.force_login(fiche['comptes']['su'])
    page = client.post(_url_mdp(fiche['membre'])).content.decode()
    assert '<html' in page and 'data-mdp=' in page
    fragment = client.post(_url_mdp(fiche['membre']), HTTP_HX_REQUEST='true').content.decode()
    assert '<html' not in fragment and 'data-mdp=' in fragment


def test_F20_2c_mdp_rediffuse_un_nouveau_mot_de_passe_et_l_ancien_cesse(client, fiche):
    m = fiche['membre']
    a = definir_mot_de_passe_membre(fiche['comptes']['su'], m)
    b = definir_mot_de_passe_membre(fiche['comptes']['su'], m)
    m.refresh_from_db()
    assert a != b and check_password(b, m.password) and not check_password(a, m.password)


def test_F20_2c_mdp_commande_affiche_sur_la_sortie_standard_seulement(fiche, capsys, caplog):
    with caplog.at_level('DEBUG'):
        call_command('definir_mot_de_passe_membre', 'MBR0000009', '--auteur', fiche['comptes']['su'].username)
    sortie = capsys.readouterr().out
    clair = sortie.strip().rsplit(' ', 1)[1]
    assert clair not in caplog.text
    for ligne in JournalAction.objects.all():
        assert clair not in ' '.join(str(getattr(ligne, f.name)) for f in ligne._meta.fields)


def test_F20_2c_page_du_mot_de_passe_mobile_non_mise_en_cache(client, fiche):
    client.force_login(fiche['comptes']['su'])
    r = client.post(_url_mdp(fiche['membre']))
    assert _mdp_affiche(r.content.decode()) and 'no-store' in r.get('Cache-Control', '')


def test_F20_2c_erreurs_du_mot_de_passe_mobile_sont_de_simples_messages(client, fiche):
    """Membre sans identifiant mobile, membre supprimé : message d'erreur ordinaire, aucun encart de mot de passe."""
    client.force_login(fiche['comptes']['su'])
    Membre.objects.filter(pk=fiche['membre'].pk).update(idf=None)
    r = client.post(_url_mdp(fiche['membre']), follow=True)
    corps = unescape(r.content.decode())
    assert "n'a pas d'identifiant mobile" in corps and 'data-mdp=' not in corps and 'Mot de passe mobile défini' not in corps
    Membre.objects.filter(pk=fiche['membre'].pk).update(idf='MBR0000009', is_delete=True)
    r = client.post(_url_mdp(fiche['membre']), follow=True)
    assert 'data-mdp=' not in r.content.decode() and not Membre.objects.get(pk=fiche['membre'].pk).password


# ---------------------------------------------------------------- gabarits sans /media/

@pytest.fixture
def avec_photo(fiche, settings, tmp_path):
    import io

    from PIL import Image
    settings.PRIVATE_MEDIA_ROOT = tmp_path / 'prive'
    t = io.BytesIO()
    Image.new('RGB', (200, 200)).save(t, 'JPEG')
    m = fiche['membre']
    m.photo = SimpleUploadedFile('p.jpg', t.getvalue())
    m.save()
    m.refresh_from_db()
    return fiche


@pytest.mark.parametrize('route, kw, htmx', [
    ('liste-membre', {}, False), ('liste-membre', {}, True), ('membre-view', 'membre', False),
    ('membre-view', 'membre', True), ('tableau-bord', {}, False), ('str-list', {}, False),
])
def test_F22_2c_gabarits_aucun_media_ni_url_directe(client, avec_photo, route, kw, htmx):
    client.force_login(avec_photo['comptes']['su'])
    kwargs = {'id': avec_photo['membre'].id} if kw == 'membre' else kw
    r = client.get(reverse(route, kwargs=kwargs), **({'HTTP_HX_REQUEST': 'true'} if htmx else {}))
    corps = r.content.decode()
    assert r.status_code == 200
    assert '/media/' not in corps
    nom = avec_photo['membre'].photo.name.lstrip('./')
    assert nom not in corps  # le nom stocké ne fuit pas dans le HTML


def test_F22_2c_gabarits_fiche_et_liste_utilisent_la_vue_controlee(client, avec_photo):
    client.force_login(avec_photo['comptes']['su'])
    m = avec_photo['membre'].id
    fiche_html = client.get(reverse('membre-view', kwargs={'id': m})).content.decode()
    liste_html = client.get(reverse('liste-membre')).content.decode()
    assert f'/fichiers/membre/{m}/photo/' in fiche_html
    assert f'/fichiers/membre/{m}/photo/?vignette=1' in liste_html or f'/fichiers/membre/{m}/photo/?vignette=1' in fiche_html


def test_F22_2c_aucun_gabarit_ne_lit_l_url_directe_d_une_photo_ou_piece_de_membre():
    interdit = re.compile(r"(membre|m|member|obj|association|structure|asso)\.(photo|fiche_id|capture_justice|preuve_de_paiement)\.url")
    fautifs = []
    for racine in ('coptapp/templates', 'templates', 'mobapp/templates', 'compte/templates', 'virtrine/templates'):
        for chemin in Path(racine).rglob('*.html'):
            texte = chemin.read_text(encoding='utf-8')
            if interdit.search(texte):
                fautifs.append(str(chemin))
    assert not fautifs, fautifs
