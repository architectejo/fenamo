"""F-40, F-62, F-67 : contexte commun du menu, historique des bascules, toasts détaillés, nombre de destinataires, signature."""
import json

from django.test import Client
from django.urls import reverse

from compte import roles
from compte.models import Compte
from compte.services.journal import identifiant_affichable
from coptapp.models import Communique
from coptapp.services import communiques as S
from tests.test_F02_droits_roles import acteurs_roles, monde  # noqa: F401
from tests.test_F40_communiques import equipe  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401
from virtrine.models import Contact
from virtrine.services import contenu
from virtrine.services.etat_donnees_reelles import etat_donnees_reelles

HX = {'HTTP_HX_REQUEST': 'true'}


def _toast(reponse):
    return json.loads(reponse['HX-Trigger'])['toast']


def test_F62_menu_nombre_a_traiter_reserve_aux_editeurs_et_su(client, acteurs_roles, monde):
    Contact.objects.all().delete()
    Contact.objects.create(nom='A', description='x' * 12)
    Contact.objects.create(nom='B', description='x' * 12, traiter=True)
    client.force_login(acteurs_roles['ED'])
    assert client.get(reverse('site')).context['nb_a_traiter_menu'] == 1
    assert client.get(reverse('site')).context['nb_a_traiter'] == 1
    client.force_login(monde['compte'])
    assert client.get(reverse('site')).context['nb_a_traiter_menu'] == 1
    client.force_login(acteurs_roles['VA'])
    assert 'nb_a_traiter_menu' not in client.get(reverse('list-message')).context


def test_F67_historique_cinq_dernieres_bascules_avec_auteur(monde):
    su = monde['compte']
    for i in range(7):
        contenu.definir_donnees_reelles(su, i % 2 == 0, f'motif {i}')
    etat = etat_donnees_reelles()
    h = etat['historique']
    assert len(h) == 5 and [x['motif'] for x in h] == [f'motif {i}' for i in (6, 5, 4, 3, 2)]
    assert [x['actif'] for x in h] == [True, False, True, False, True]
    assert etat['par'] == h[0]['par'] and etat['motif'] == 'motif 6' and etat['depuis'] == h[0]['date']
    assert h[0]['par'] in (su.get_full_name(), identifiant_affichable(su))


def test_F67_historique_vide_sans_bascule(db):
    assert etat_donnees_reelles()['historique'] == []


def test_F67_toast_detaille_donnees_reelles(client, monde):
    client.force_login(monde['compte'])
    r = client.post(reverse('donnees-reelles'), {'actif': '1'}, **HX)
    assert r.status_code == 204 and _toast(r)['message'] == 'Données réelles activées' and 'données réelles' in _toast(r)['detail']
    r = client.post(reverse('donnees-reelles'), {'actif': '0'}, **HX)
    assert _toast(r)['message'] == "Données d'exemple rétablies" and "jeu d'exemple" in _toast(r)['detail']


def test_F62_toast_il_reste_n_messages(client, acteurs_roles):
    Contact.objects.all().delete()
    a = Contact.objects.create(nom='A', description='x' * 12)
    Contact.objects.create(nom='B', description='x' * 12)
    Contact.objects.create(nom='C', description='x' * 12)
    client.force_login(acteurs_roles['ED'])
    r = client.post(reverse('contact-view', kwargs={'id': a.pk}), **HX)
    assert _toast(r)['message'] == 'Message marqué comme traité' and _toast(r)['detail'] == 'Il reste 2 messages à traiter.'


def test_F40_apercu_destinataires_et_toast_de_publication(client, monde, equipe):
    ed = equipe['ED']
    attendu = S.apercu_destinataires(ed, 'coordination', monde['P'])['nombre']
    assert attendu >= 1
    client.force_login(ed)
    r = client.get(reverse('message'), {'cible': 'coordination', 'coordination': monde['P'].pk}, **HX)
    assert r.context['nb_destinataires'] == attendu
    r = client.get(reverse('message'), {'cible': 'antenne'}, **HX)  # choix incomplet : pas de nombre, message d'erreur
    assert 'nb_destinataires' not in r.context and "Choisissez l'antenne" in r.context['apercu_erreur']
    nationaux = S.apercu_destinataires(ed, 'national')['nombre']
    ok = client.post(reverse('message'), {'titre': 'T', 'message': 'M', 'cible': 'coordination', 'coordination': monde['P'].pk}, **HX)
    toast = _toast(ok)
    assert toast['message'] == 'Communiqué publié' and f'{attendu} compte' in toast['detail'] and monde['P'].nom in toast['detail']
    assert nationaux >= attendu
    ok = client.post(reverse('message'), {'titre': 'T2', 'message': 'M', 'cible': 'national'}, **HX)
    assert 'à toute la fédération' in _toast(ok)['detail']


def test_F40_signature_role_de_l_auteur(client, monde, equipe):
    c = S.publier(equipe['ED'], 'Signé', 'm')
    client.force_login(equipe['VA_P'])
    r = client.get(reverse('communique', kwargs={'id': c.pk}))
    assert r.context['auteur_role'] == roles.LIBELLES[roles.ED]
    assert S.role_libelle(None) == ''
    assert S.role_libelle(Compte.objects.create_user('sans-role-x', password='x')) == ''
