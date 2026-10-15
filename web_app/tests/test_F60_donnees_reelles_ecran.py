"""F-60 : écran de l'interrupteur « Données réelles du site » (carte d'état, modale, bascule par événement), super-utilisateur seul."""
from django.test import Client
from django.urls import reverse

from compte import roles
from compte.models import Compte, JournalAction, Nomination
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401
from virtrine.models import Config

HX = {'HTTP_HX_REQUEST': 'true'}
SCRIPT = '<script>alert(1)</script>'


def _editeur(jeu):
    c = Compte.objects.create_user('editeur-dr', password='x')
    Nomination.objects.create(compte=c, role=roles.ED, nomme_par=jeu['compte'])
    return c


def test_F60_carte_visible_au_su_seulement(client, jeu):
    client.force_login(jeu['compte'])
    html = client.get(reverse('site')).content.decode()
    assert 'donnees-reelles-zone' in html and 'Données du site public' in html and ('Données d&#x27;exemple' in html or "Données d'exemple" in html)
    assert 'Réglage d' in html and reverse('donnees-reelles') in html
    client.force_login(_editeur(jeu))
    r = client.get(reverse('site'))
    assert r.status_code == 200 and 'donnees-reelles' not in r.content.decode()


def test_F60_modale_avertissement_a_l_activation_puis_retour(client, jeu):
    client.force_login(jeu['compte'])
    html = client.get(reverse('donnees-reelles'), **HX).content.decode()
    assert 'name="actif" value="1"' in html and 'visibles par tout le monde' in html and 'data-compte-caracteres' in html and 'maxlength="500"' in html
    Config.instance().__class__.objects.update(donnees_reelles_actif=True)
    html = client.get(reverse('donnees-reelles'), **HX).content.decode()
    assert 'name="actif" value="0"' in html and 'visibles par tout le monde' not in html


def test_F60_post_nominal_evenement_journal_et_carte_mise_a_jour(client, jeu):
    client.force_login(jeu['compte'])
    r = client.post(reverse('donnees-reelles'), {'actif': '1', 'motif': SCRIPT}, **HX)
    assert r.status_code == 204 and 'donneesReellesModifiees' in r['HX-Trigger']
    assert Config.instance().donnees_reelles_actif is True
    carte = client.get(reverse('donnees-reelles-etat'), **HX).content.decode()
    assert 'Données réelles' in carte and ' change"' in carte and 'Depuis le' in carte and 'admin-test' in carte and 'verrou--ferme' in carte
    assert SCRIPT not in carte and '&lt;script&gt;' in carte  # motif échappé, jamais |safe
    assert JournalAction.objects.filter(action='modification', objet_libelle__isnull=False).exists()
    assert 'Revenir aux données d' in carte


def test_F60_refus_et_erreurs(client, jeu):
    client.force_login(_editeur(jeu))
    for methode in (client.get, client.post):
        assert methode(reverse('donnees-reelles'), **HX).status_code == 403
    assert client.get(reverse('donnees-reelles-etat'), **HX).status_code == 403
    assert Config.instance().donnees_reelles_actif is False
    client.force_login(jeu['compte'])
    r = client.post(reverse('donnees-reelles'), {'actif': '1', 'motif': 'x' * 501}, **HX)
    assert r.status_code == 422 and 'limité à 500' in r.content.decode()
    assert client.post(reverse('donnees-reelles-etat')).status_code == 405


def test_F60_csrf_exige(jeu):
    c = Client(enforce_csrf_checks=True)
    c.force_login(jeu['compte'])
    assert c.post(reverse('donnees-reelles'), {'actif': '1'}, **HX).status_code == 403
    assert Config.instance().donnees_reelles_actif is False
