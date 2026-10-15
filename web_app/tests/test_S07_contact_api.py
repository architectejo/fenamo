"""S-07 / F-62 : POST /api/v1/site/contact/ (clé, limite, anti-spam, validation, XSS, verrou F-07, mode exemple) et consultation des messages."""
import json
import time

import pytest
from django.core.cache import caches
from django.test import Client
from django.urls import reverse

from api.services import cles
from compte.models import JournalAction
from compte.services import verrou_application as V
from coptapp.models import Notification
from tests.test_F02_droits_roles import acteurs_roles, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401
from virtrine.models import Config, Contact

URL = '/api/v1/site/contact/'


@pytest.fixture(autouse=True)
def cache_propre(db):
    caches['limites'].clear()


@pytest.fixture
def cle(db):
    config = Config.instance()
    config.donnees_reelles_actif = True
    config.save(update_fields=['donnees_reelles_actif'])
    return cles.creer_cle('Site public')[1]


def valide(**surcharge):
    donnees = {'nom': 'Jean Mukendi', 'mail': 'jean@example.org', 'telephone': '', 'objet': 'Question sur l\'adhésion',
               'message': 'Bonjour, comment adhérer à la fédération ?', 'site_web': '', 'ouvert_le': time.time() - 30}
    donnees.update(surcharge)
    return donnees


def envoyer(client, donnees, cle=None, json_=True):
    entetes = {'HTTP_X_SITE_KEY': cle} if cle else {}
    if json_:
        return client.post(URL, json.dumps(donnees), content_type='application/json', **entetes)
    return client.post(URL, donnees, **entetes)


def corps(reponse):
    return json.loads(reponse.content)


# ---------------------------------------------------------------- nominal

def test_S07_nominal_json_201_enregistre_journalise_notifie(client, cle):
    r = envoyer(client, valide(), cle)
    assert r.status_code == 201 and r['Content-Type'].startswith('application/json')
    assert set(corps(r)) == {'statut', 'detail'} and corps(r)['statut'] == 'recu'
    assert 'Set-Cookie' not in r.headers and 'no-cache' in r['Cache-Control']
    c = Contact.objects.get()
    assert (c.nom, c.mail, c.raison, c.traiter) == ('Jean Mukendi', 'jean@example.org', "Question sur l'adhésion", False)
    assert c.cree_le is not None and c.phone is None
    ligne = JournalAction.objects.get(action='creation')
    assert ligne.auteur is None and ligne.objet_id == c.pk
    texte = json.dumps([ligne.avant, ligne.apres, ligne.objet_libelle, ligne.motif], ensure_ascii=False)
    for secret in ('Jean', 'Mukendi', 'jean@example.org', 'Bonjour', 'adhésion'):
        assert secret not in texte  # aucune donnée personnelle ni texte du message au journal
    assert Notification.objects.filter(titre='Nouveau message du site').count() == 1
    notif = Notification.objects.get()
    assert 'Jean' not in notif.description and 'jean@' not in notif.description


def test_S07_nominal_formulaire_encode_et_telephone_seul(client, cle):
    r = envoyer(client, valide(mail='', telephone='+243 81 234 5678'), cle, json_=False)
    assert r.status_code == 201
    assert Contact.objects.get().phone == '+243 81 234 5678'


def test_S07_reponse_sans_identifiant_ni_donnee_saisie(client, cle):
    donnees = corps(envoyer(client, valide(), cle))
    brut = json.dumps(donnees)
    assert 'id' not in donnees and 'jean@example.org' not in brut and 'Mukendi' not in brut


# ---------------------------------------------------------------- clé, méthode, débit

def test_S07_sans_cle_ou_cle_invalide_401_rien_enregistre(client, cle):
    assert envoyer(client, valide()).status_code == 401
    r = envoyer(client, valide(), cle[:-3] + 'xyz')
    assert r.status_code == 401 and corps(r) == {'detail': 'Clé du site absente ou invalide.'}
    assert not Contact.objects.exists()


def test_S07_methodes_autres_que_post_405(client, cle):
    for methode in ('get', 'put', 'delete'):
        r = getattr(client, methode)(URL, HTTP_X_SITE_KEY=cle)
        assert r.status_code == 405 and r['Allow'] == 'POST'


def test_S07_limite_de_debit_de_la_cle_429(client, cle, settings):
    settings.SITE_API_LIMITE_POST = 2
    codes = [envoyer(client, valide(mail=f'a{i}@example.org'), cle).status_code for i in range(3)]
    assert codes == [201, 201, 429]
    r = envoyer(client, valide(mail='z@example.org'), cle)
    assert r.status_code == 429 and 'Retry-After' in r.headers and Contact.objects.count() == 2


def test_S07_limite_par_contact_429_au_quatrieme_message_du_meme_expediteur(client, cle):
    codes = [envoyer(client, valide(), cle).status_code for _ in range(4)]
    assert codes == [201, 201, 201, 429]
    assert Contact.objects.count() == 3
    assert envoyer(client, valide(mail='autre@example.org'), cle).status_code == 201


# ---------------------------------------------------------------- anti-spam

def test_S07_champ_piege_rempli_faux_succes_sans_rien_enregistrer(client, cle):
    r = envoyer(client, valide(site_web='http://spam.example'), cle)
    assert r.status_code == 201 and corps(r)['statut'] == 'recu'
    assert not Contact.objects.exists() and not Notification.objects.exists()


def test_S07_envoi_trop_rapide_400(client, cle):
    r = envoyer(client, valide(ouvert_le=time.time()), cle)
    assert r.status_code == 400 and 'non_field_errors' in corps(r) and not Contact.objects.exists()


@pytest.mark.parametrize('valeur', [None, 'abc', time.time() - 90000, time.time() + 3600, True, [1]])
def test_S07_horodatage_absent_absurde_ou_expire_400(client, cle, valeur):
    d = valide()
    if valeur is None:
        d.pop('ouvert_le')
    else:
        d['ouvert_le'] = valeur
    r = envoyer(client, d, cle)
    assert r.status_code == 400 and 'ouvert_le' in corps(r) and not Contact.objects.exists()


# ---------------------------------------------------------------- validation stricte

@pytest.mark.parametrize('surcharge, champ', [
    ({'nom': ''}, 'nom'), ({'nom': 'A'}, 'nom'), ({'nom': 'x' * 101}, 'nom'),
    ({'objet': ''}, 'objet'), ({'objet': 'x' * 101}, 'objet'),
    ({'message': ''}, 'message'), ({'message': 'court'}, 'message'), ({'message': 'x' * 3001}, 'message'),
    ({'message': 'voir http://a.example http://b.example http://c.example'}, 'message'),
    ({'mail': 'pas-un-mail'}, 'mail'), ({'mail': 'a@' + 'b' * 260 + '.org'}, 'mail'),
    ({'mail': '', 'telephone': 'abc123'}, 'telephone'), ({'mail': '', 'telephone': '1234'}, 'telephone'),
    ({'mail': '', 'telephone': '+' + '1' * 25}, 'telephone'),
    ({'nom': ['liste']}, 'nom'), ({'message': {'a': 1}}, 'message'), ({'objet': 12}, 'objet'),
    ({'mail': '', 'telephone': ''}, 'non_field_errors'),
])
def test_S07_validation_400_champ_liste_de_messages(client, cle, surcharge, champ):
    r = envoyer(client, valide(**surcharge), cle)
    assert r.status_code == 400
    donnees = corps(r)
    assert champ in donnees and isinstance(donnees[champ], list) and all(isinstance(m, str) and m for m in donnees[champ])
    assert not Contact.objects.exists()


def test_S07_plusieurs_erreurs_a_la_fois_et_champs_inconnus_ignores(client, cle):
    r = envoyer(client, valide(nom='', objet='', is_staff=True, traiter=True, id=99), cle)
    assert r.status_code == 400 and {'nom', 'objet'} <= set(corps(r))
    assert envoyer(client, valide(traiter=True, id=99, cree_le='2000-01-01'), cle).status_code == 201
    c = Contact.objects.get()
    assert c.traiter is False and c.pk != 99


def test_S07_corps_illisible_ou_non_objet_400(client, cle):
    for brut in ('pas du json', '[1, 2]', '"texte"'):
        r = client.post(URL, brut, content_type='application/json', HTTP_X_SITE_KEY=cle)
        assert r.status_code == 400 and 'non_field_errors' in corps(r)


def test_S07_corps_trop_gros_413(client, cle):
    r = envoyer(client, valide(message='x' * 30_000), cle)
    assert r.status_code == 413 and corps(r) == {'detail': 'Requête trop volumineuse.'}
    assert not Contact.objects.exists()


# ---------------------------------------------------------------- XSS : aucun HTML conservé

@pytest.mark.parametrize('charge', [
    '<script>alert(1)</script>Bonjour tout le monde',
    '<img src=x onerror=alert(1)>Bonjour tout le monde',
    '<b onclick="x()">Bonjour</b> tout le monde',
    '&lt;script&gt;alert(1)&lt;/script&gt; Bonjour tout le monde',
    '<<script>script>alert(1)<</script>/script>Bonjour tout le monde',
    '<style>body{display:none}</style>Bonjour tout le monde',
    '<!-- commentaire -->Bonjour <a href="javascript:alert(1)">tout</a> le monde',
])
def test_S07_aucun_html_conserve_dans_aucun_champ(client, cle, charge):
    r = envoyer(client, valide(nom=charge[:60] + ' Dupont', objet=charge[:90], message=charge), cle)
    assert r.status_code == 201, corps(r)
    c = Contact.objects.get()
    for valeur in (c.nom, c.raison, c.description):
        assert '<' not in valeur and '>' not in valeur
        assert 'alert(1)</' not in valeur and 'display:none' not in valeur
    assert 'Bonjour' in c.description


def test_S07_message_reduit_a_du_html_vide_est_refuse(client, cle):
    r = envoyer(client, valide(message='<script>alert(1)</script><b></b>'), cle)
    assert r.status_code == 400 and 'message' in corps(r)


def test_S07_caracteres_de_controle_retires_retours_a_la_ligne_gardes(client, cle):
    envoyer(client, valide(message='Ligne un\x00 bien‮\n\n\n\nLigne deux assez longue', nom='Jean\nMukendi'), cle)
    c = Contact.objects.get()
    assert '\x00' not in c.description and '‮' not in c.description
    assert c.description == 'Ligne un bien\n\nLigne deux assez longue' and c.nom == 'Jean Mukendi'


def test_S07_affichage_back_office_echappe(client, cle, monde):
    envoyer(client, valide(message='Bonjour <script>alert(1)</script> le monde'), cle)
    client.force_login(monde['compte'])
    c = Contact.objects.get(raison="Question sur l'adhésion")
    assert b'<script>alert(1)' not in client.get(reverse('contact-view', kwargs={'id': c.pk})).content
    assert b'<script>alert(1)' not in client.get(reverse('contact')).content


# ---------------------------------------------------------------- verrou F-07 et mode exemple

def test_S07_application_verrouillee_503_rien_enregistre(client, cle, monde):
    avant = Contact.objects.count()  # le jeu d'essai contient déjà un message
    V.verrouiller(monde['compte'], 'Maintenance.', 'secret')
    r = envoyer(client, valide(), cle)
    assert r.status_code == 503 and corps(r) == {'statut': 'suspendu', 'detail': 'Service suspendu.', 'message': 'Maintenance.'}
    assert Contact.objects.count() == avant


def test_S07_mode_exemple_403_inactif_rien_enregistre(client, cle):
    config = Config.instance()
    config.donnees_reelles_actif = False
    config.save(update_fields=['donnees_reelles_actif'])
    r = envoyer(client, valide(), cle)
    assert r.status_code == 403 and corps(r) == {'statut': 'inactif', 'detail': 'Données réelles désactivées.'}
    assert not Contact.objects.exists() and not Notification.objects.exists()


# ---------------------------------------------------------------- consultation (F-62) : droits, CSRF, POST seulement

def _message(**kw):
    return Contact.objects.create(nom='Visiteur', mail='v@example.org', raison='Objet', description='Texte du message', **kw)


def test_F62_liste_et_fiche_editeur_et_su_seulement(client, acteurs_roles, monde):
    c = _message()
    for role, attendu in {'ED': 200, 'PR': 403, 'VN': 403, 'VP': 403, 'VA': 403, 'AT': 403, 'VI': 403}.items():
        client.force_login(acteurs_roles[role])
        assert client.get(reverse('contact')).status_code == attendu, role
        assert client.get(reverse('contact-view', kwargs={'id': c.pk})).status_code == attendu, role
    client.force_login(monde['compte'])
    assert client.get(reverse('contact')).status_code == 200
    client.logout()
    assert client.get(reverse('contact')).status_code == 302  # anonyme : connexion


def test_F62_marquer_traite_post_seulement_csrf_journal_idempotent(acteurs_roles, monde):
    c = _message()
    url = reverse('contact-view', kwargs={'id': c.pk})
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(acteurs_roles['ED'])
    assert strict.post(url).status_code == 403  # sans jeton CSRF
    strict.get(url)
    c.refresh_from_db()
    assert not c.traiter  # un GET ne modifie rien
    jeton = strict.cookies['csrftoken'].value  # posé par la page (get_token dans le gabarit)
    assert strict.post(url, HTTP_X_CSRFTOKEN=jeton).status_code == 200
    c.refresh_from_db()
    assert c.traiter and c.traite_par == acteurs_roles['ED'] and c.traite_le is not None
    assert JournalAction.objects.filter(action='modification', objet_id=c.pk).count() == 1
    strict.post(url, HTTP_X_CSRFTOKEN=jeton)
    assert JournalAction.objects.filter(action='modification', objet_id=c.pk).count() == 1  # idempotent


def test_F62_marquer_traite_refuse_sans_droit_et_aucun_effet(client, acteurs_roles):
    c = _message()
    url = reverse('contact-view', kwargs={'id': c.pk})
    for role in ('VA', 'VI', 'PR'):
        client.force_login(acteurs_roles[role])
        assert client.post(url).status_code == 403
    c.refresh_from_db()
    assert not c.traiter and not JournalAction.objects.filter(action='modification').exists()


def test_F62_marquer_traite_editeur_ok_et_message_inconnu_404(client, acteurs_roles):
    c = _message()
    client.force_login(acteurs_roles['ED'])
    assert client.post(reverse('contact-view', kwargs={'id': c.pk})).status_code == 200
    c.refresh_from_db()
    assert c.traiter and c.traite_par == acteurs_roles['ED']
    assert client.post(reverse('contact-view', kwargs={'id': 99999})).status_code == 404


def test_F62_liste_paginee_contexte(client, monde):
    for i in range(30):
        Contact.objects.create(nom=f'V{i}', description='x' * 12)
    client.force_login(monde['compte'])
    r = client.get(reverse('contact'))
    assert len(r.context['contacts']) == 25 and r.context['page_obj'].paginator.num_pages == 2 and r.context['nb_a_traiter'] == Contact.objects.count()
    assert len(client.get(reverse('contact') + '?page=2').context['contacts']) == Contact.objects.count() - 25
    assert client.get(reverse('contact') + '?page=abc').status_code == 200


def test_F62_filtres_recherche_et_nombres(client, monde):
    Contact.objects.all().delete()  # le jeu d'essai en contient déjà
    a = Contact.objects.create(nom='Aimé Kasa', mail='a@x.org', phone='0810000001', raison='Adhésion', description='x' * 12)
    b = Contact.objects.create(nom='Bob', mail='b@x.org', phone='0820000002', raison='Presse', description='x' * 12, traiter=True)
    client.force_login(monde['compte'])
    r = client.get(reverse('contact'))
    assert [c.pk for c in r.context['contacts']] == [a.pk] and r.context['filtres']['etat'] == 'a_traiter'  # défaut : à traiter
    assert r.context['nombres'] == {'a_traiter': 1, 'traites': 1, 'tous': 2}
    assert [c.pk for c in client.get(reverse('contact'), {'etat': 'traites'}).context['contacts']] == [b.pk]
    assert {c.pk for c in client.get(reverse('contact'), {'etat': 'tous'}).context['contacts']} == {a.pk, b.pk}
    assert client.get(reverse('contact'), {'etat': 'n_importe_quoi'}).context['filtres']['etat'] == 'a_traiter'
    for q, attendu in (('aimé', a.pk), ('0820', b.pk), ('b@x', b.pk), ('presse', b.pk)):
        trouves = client.get(reverse('contact'), {'q': q, 'etat': 'tous'}).context['contacts']
        assert [c.pk for c in trouves] == [attendu], q
    assert client.get(reverse('contact'), {'q': 'bob'}).context['nombres'] == {'a_traiter': 0, 'traites': 1, 'tous': 1}
    assert client.get(reverse('contact'), HTTP_HX_REQUEST='true').status_code == 200  # fragment (ou page tant que le gabarit manque)


def test_F62_recu_le_ne_bouge_pas_et_traitement_trace(client, acteurs_roles):
    from datetime import timedelta
    from django.utils import timezone
    Contact.objects.all().delete()  # le jeu d'essai en contient déjà
    reception = timezone.now() - timedelta(days=3)
    c = _message(cree_le=reception)
    autre = _message()
    client.force_login(acteurs_roles['ED'])
    url = reverse('contact-view', kwargs={'id': c.pk})
    avant = client.get(url)
    assert avant.context['recu_le'] == reception and avant.context['suivant'].pk == autre.pk and avant.context['nb_a_traiter'] == 2
    r = client.post(url, HTTP_HX_REQUEST='true')
    assert r.status_code == 200 and 'toast' in r['HX-Trigger'] and r.context['vient_de_traiter'] is True
    assert r.context['recu_le'] == reception and r.context['traite_par'] == acteurs_roles['ED'] and r.context['traite_le'] is not None
    assert r.context['nb_a_traiter'] == 1
    assert 'toast' not in client.post(url, HTTP_HX_REQUEST='true').headers.get('HX-Trigger', '')  # idempotent : pas de second toast
