"""Validation indépendante 2e (testeur) : critères de fin du sous-lot « rôles, nominations, écran Utilisateurs » (F-02, F-03, F-05, F-06).

Les défauts relevés par ce lot ont tous été corrigés : plus aucun test n'est marqué en échec attendu.
"""
import io
import json
import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from django.contrib.messages import get_messages
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from compte import roles
from compte.models import Compte, JournalAction, Nomination
from compte.services import nominations as noms
from compte.services.droits import droits_membre, etapes_a_valider, membres_du_perimetre, profil_de
from compte.services.nominations import creer_nomination
from coptapp.models import Antenne, Membre, Notification, Province, Ville
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401



@pytest.fixture
def monde(jeu):
    P = jeu['province']
    Q = Province.objects.create(nom='Quest', sigle='QU', code='QU')
    Antenne.objects.filter(pk=jeu['antenne'].pk).update(coordination=P)
    A = Antenne.objects.get(pk=jeu['antenne'].pk)
    A2 = Antenne.objects.create(nom='Antenne A2', coordination=P)
    ville_q = Ville.objects.create(nom='Ville Q', province=Q)
    AQ = Antenne.objects.create(nom='Antenne Q', coordination=Q, ville_origine=ville_q)
    su = jeu['compte']

    def nommer(nom, role, **perimetre):
        c = Compte.objects.create_user(nom, password='x')
        creer_nomination(su, c, role, **perimetre)
        return Compte.objects.get(pk=c.pk)

    def membre(nom, antenne, province, **kw):
        return Membre.objects.create(nom=nom, province=province, antenne=antenne, **kw)

    comptes = {'su': su, 'pr': nommer('pr', roles.PR), 'vn': nommer('vn', roles.VN), 'vp': nommer('vp', roles.VP, coordination=P),
               'va': nommer('va', roles.VA, antenne=A), 'at': nommer('at', roles.AT, antenne=A), 'vi': nommer('vi', roles.VI),
               'ed': nommer('ed', roles.ED), 'vi_a': nommer('vi_a', roles.VI, antenne=A),
               'vi_p': nommer('vi_p', roles.VI, coordination=P), 'vp_q': nommer('vp_q', roles.VP, coordination=Q)}
    membres = {
        'actif_a': membre('Actif A', A, P, is_validate1=True, is_validate2=True, is_validate3=True),
        'saisi_a': membre('Saisi A', A, P),  # non actif
        'v2_a': membre('Valide 2 A', A, P, is_validate2=True),
        'actif_a2': membre('Actif A2', A2, P, is_validate2=True, is_validate3=True),
        'actif_q': membre('Actif Q', AQ, Q, ville=ville_q, is_validate2=True, is_validate3=True),
        'saisi_q': membre('Saisi Q', AQ, Q, ville=ville_q),
    }
    return {**jeu, 'P': P, 'Q': Q, 'A': A, 'A2': A2, 'AQ': AQ, 'comptes': comptes, 'm': membres}


def _noms(qs):
    return sorted(qs.values_list('nom', flat=True))


# ================================================================ 1. aucun privilegeN lu hors droits_herites.py / compte

AUTORISES = ('compte/', 'compte\\', 'tests/', 'tests\\', 'migrations')
MOTIF_PRIVILEGE = re.compile(r"""(?<![\w.])(?:user|request\.user|auteur|compte|u|c)\.(?:privilege[1-5]?|editor)\b|"""
                             r"""getattr\(\s*[^,()]+,\s*f?['"]privilege""")


def _fichiers_a_auditer():
    racine = Path('.')
    for dossier in ('coptapp', 'fenamo', 'mobapp', 'api', 'virtrine', 'templates'):
        for chemin in Path(dossier).rglob('*'):
            if chemin.suffix in ('.py', '.html') and '__pycache__' not in chemin.parts and 'migrations' not in chemin.parts:
                yield chemin
    assert racine.exists()


def test_F02_2e_aucun_privilege_lu_hors_droits_herites_et_compte():
    fautifs = []
    for chemin in _fichiers_a_auditer():
        for numero, ligne in enumerate(chemin.read_text(encoding='utf-8', errors='ignore').splitlines(), start=1):
            if ligne.lstrip().startswith(('#', '"""', '{#')):
                continue
            if MOTIF_PRIVILEGE.search(ligne):
                fautifs.append(f'{chemin.as_posix()}:{numero}')
    assert not fautifs, fautifs


def test_F02_2e_lectures_de_privileges_hors_modules_autorises_sont_connues():
    """Garde-fou : la liste des lectures restantes ne grandit pas (aujourd'hui : myNotify et le menu hérité)."""
    trouvees = set()
    for chemin in _fichiers_a_auditer():
        for ligne in chemin.read_text(encoding='utf-8', errors='ignore').splitlines():
            if not ligne.lstrip().startswith(('#', '"""', '{#')) and MOTIF_PRIVILEGE.search(ligne):
                trouvees.add(chemin.as_posix())
    assert trouvees <= {'coptapp/views/__init__.py', 'coptapp/templates/app/header.html'}, sorted(trouvees)


# ================================================================ 2. FENAMO_DROITS_HERITES

def _herite(monde, **privileges):
    c = Compte.objects.create_user('herite', password='x', membreId=monde['m']['saisi_a'].id, **privileges)
    return Compte.objects.get(pk=c.pk)


def test_F02_2e_herites_vrai_les_privileges_donnent_leurs_droits(monde, settings):
    settings.FENAMO_DROITS_HERITES = True
    c = _herite(monde, privilege5=True)
    assert profil_de(c).mode == 'herite'
    assert membres_du_perimetre(c).count() == Membre.objects.filter(is_delete=False).count()


def test_F02_2e_herites_faux_un_compte_sans_nomination_ne_voit_que_sa_fiche(monde, settings):
    settings.FENAMO_DROITS_HERITES = False
    for privileges in ({'privilege1': True}, {'privilege2': True}, {'privilege3': True}, {'privilege4': True},
                       {'privilege5': True}, {'privilege1': True, 'privilege5': True, 'editor': True}):
        Compte.objects.filter(username='herite').delete()
        c = _herite(monde, **privileges)
        assert profil_de(c).mode == 'fiche', privileges
        assert _noms(membres_du_perimetre(c)) == ['Saisi A'], privileges  # sa seule fiche
        autre = monde['m']['actif_a']
        droits = droits_membre(c, autre)
        assert not any(droits.values()), privileges
        assert etapes_a_valider(c, autre) == []


def test_F02_2e_herites_faux_vues_fermees_au_compte_sans_nomination(client, monde, settings):
    settings.FENAMO_DROITS_HERITES = False
    c = _herite(monde, privilege5=True, privilege3=True, editor=True)
    client.force_login(c)
    assert client.get(reverse('membre-view', kwargs={'id': monde['m']['actif_a'].id})).status_code == 404
    assert client.post(reverse('validate', kwargs={'id': monde['m']['actif_a'].id})).status_code in (403, 404)
    assert client.get(reverse('add-fenamo-membre')).status_code == 403
    assert client.get(reverse('add-structure')).status_code in (403, 404)
    assert client.get(reverse('site')).status_code == 403  # champ « editor » ignoré
    assert client.get(reverse('utilisateurs')).status_code == 403
    page = client.get(reverse('liste-membre')).content.decode()
    assert 'Actif A' not in page and 'Actif Q' not in page


def test_F02_2e_herites_faux_ne_touche_ni_le_su_ni_les_comptes_nommes(client, monde, settings):
    settings.FENAMO_DROITS_HERITES = False
    assert profil_de(monde['comptes']['su']).mode == 'su'
    assert _noms(membres_du_perimetre(monde['comptes']['su'])) == sorted(Membre.objects.values_list('nom', flat=True))
    assert profil_de(monde['comptes']['va']).mode == 'nomination'
    assert 'Actif A' in _noms(membres_du_perimetre(monde['comptes']['va']))


def test_F02_2e_herites_faux_aucun_privilege_ne_s_ajoute_a_une_nomination(monde, settings):
    """Un agent (AT) qui porte aussi privilege5 ou privilege3 garde les droits de son rôle, ni plus ni moins."""
    for etat in (True, False):
        settings.FENAMO_DROITS_HERITES = etat
        at = Compte.objects.get(username='at')
        Compte.objects.filter(pk=at.pk).update(privilege5=True, privilege3=True, editor=True)
        at = Compte.objects.get(pk=at.pk)
        assert 'Actif Q' not in _noms(membres_du_perimetre(at))  # AT : lit son antenne seulement (jamais une autre coordination)
        assert not droits_membre(at, monde['m']['actif_a'])['peut_valider']
        from compte.services.droits import est_editeur, peut_ecrire_referentiel
        assert not est_editeur(at) and not peut_ecrire_referentiel(at)


def test_F02_2e_herites_faux_notifications_des_autres_non_visibles(client, monde, settings):
    settings.FENAMO_DROITS_HERITES = False
    c = _herite(monde, privilege5=True)
    Notification.objects.create(user=monde['comptes']['pr'], titre='SECRET-DU-PRESIDENT', description='x')
    client.force_login(c)
    assert 'SECRET-DU-PRESIDENT' not in client.get(reverse('notifys')).content.decode()


def test_F02_2e_nomination_notifications_selon_le_role_pas_le_privilege(client, monde):
    at = Compte.objects.get(username='at')
    Compte.objects.filter(pk=at.pk).update(privilege5=True)
    Notification.objects.create(user=monde['comptes']['pr'], titre='SECRET-DU-PRESIDENT', description='x')
    client.force_login(Compte.objects.get(pk=at.pk))
    assert 'SECRET-DU-PRESIDENT' not in client.get(reverse('notifys')).content.decode()


# ================================================================ 3. mot de passe temporaire : lecture unique

def _mdp_de(reponse):
    return reponse.context['valeur']


def _fuites(client, reponse, clair):
    """Liste des endroits où le mot de passe en clair apparaît (doit rester vide)."""
    trouve = []
    if any(clair in str(v) for v in reponse.headers.values()):
        trouve.append('en-têtes')
    if clair in ' '.join(m.message for m in get_messages(reponse.wsgi_request)):
        trouve.append('messages')
    if clair in json.dumps({k: str(v) for k, v in client.session.items()}):
        trouve.append('session')
    if any(clair in c.value for c in client.cookies.values()):
        trouve.append('cookies')
    for ligne in JournalAction.objects.all():
        if clair in ' '.join(str(getattr(ligne, f.name)) for f in ligne._meta.fields):
            trouve.append(f'journal #{ligne.pk}')
    return trouve


def _scenarios(monde):
    return [
        ('nommer', 'utilisateurs-nommer', None, {'membre': monde['m']['actif_a'].id, 'role': 'AT', 'antenne': monde['A'].id}),
        ('externe', 'utilisateurs-externe', None, {'username': 'ext-1', 'type': 'VI', 'portee': 'national'}),
        ('reinitialiser', 'utilisateurs-reinitialiser', 'at', {}),
    ]


@pytest.mark.parametrize('indice', [0, 1, 2])
def test_F02_2e_mot_de_passe_temporaire_jamais_dans_journal_session_messages_en_tetes(client, monde, caplog, indice):
    cle, route, cible, donnees = _scenarios(monde)[indice]
    client.force_login(monde['comptes']['su'])
    url = reverse(route, kwargs={'id': monde['comptes'][cible].id}) if cible else reverse(route)
    with caplog.at_level('DEBUG'):
        r = client.post(url, donnees)
    assert r.status_code == 200, cle
    clair = _mdp_de(r)
    assert len(clair) == 12 and not set('0O1lI') & set(clair)
    assert _fuites(client, r, clair) == []
    assert clair not in caplog.text
    assert 'no-store' in r['Cache-Control'] and 'private' in r['Cache-Control'] and 'hx-history="false"' in r.content.decode()
    assert json.loads(r['HX-Trigger']) == {'utilisateursModifies': True}
    # lecture unique : ni la liste, ni la page rechargée, ni un second GET ne le montrent ; seul le hachage est enregistré
    for adresse in (reverse('utilisateurs'), reverse('utilisateurs'), reverse('tableau-bord')):
        assert clair not in client.get(adresse).content.decode()
    compte = Compte.objects.get(username={'nommer': Compte.objects.filter(nominations__membre=monde['m']['actif_a']).first()
                                          and Compte.objects.filter(nominations__membre=monde['m']['actif_a']).first().username,
                                          'externe': 'ext-1', 'reinitialiser': 'at'}[cle])
    assert compte.password != clair and compte.check_password(clair) and compte.doit_changer_mot_de_passe


def test_F02_2e_mot_de_passe_temporaire_de_la_reactivation_seulement_sur_demande(client, monde):
    cible = monde['comptes']['at']
    Compte.objects.filter(pk=cible.pk).update(is_active=False)
    client.force_login(monde['comptes']['su'])
    url = reverse('utilisateurs-reactiver', kwargs={'id': cible.id})
    r = client.post(url, {})
    assert r.status_code == 204 and Compte.objects.get(pk=cible.pk).is_active
    assert 'valeur' not in (getattr(r, 'context', None) or {})
    Compte.objects.filter(pk=cible.pk).update(is_active=False)
    r = client.post(url, {'nouveau_mdp': '1'})
    assert r.status_code == 200 and _fuites(client, r, _mdp_de(r)) == []


def test_F02_2e_mot_de_passe_temporaire_les_erreurs_n_en_contiennent_pas(client, monde):
    client.force_login(monde['comptes']['su'])
    r = client.post(reverse('utilisateurs-externe'), {'username': 'ADMIN-TEST', 'type': 'VI'})  # existe déjà, casse différente
    assert r.status_code == 422 and Compte.objects.filter(username__iexact='admin-test').count() == 1


def test_F02_2e_journaux_de_nomination_et_reinitialisation_presents_sans_mot_de_passe(client, monde):
    client.force_login(monde['comptes']['pr'])
    r = client.post(reverse('utilisateurs-reinitialiser', kwargs={'id': monde['comptes']['at'].id}))
    clair = _mdp_de(r)
    ligne = JournalAction.objects.filter(action=JournalAction.Action.REINITIALISATION_MOT_DE_PASSE).get()
    assert ligne.auteur == monde['comptes']['pr'] and clair not in str(ligne.__dict__)


# ================================================================ 4. anti-escalade de nomination

CHOIX = {  # rôle de l'auteur -> rôles qu'il peut nommer
    'su': {'PR', 'VN', 'VP', 'VA', 'AT', 'VI', 'ED'}, 'pr': {'VN', 'VP', 'VA', 'AT', 'VI'}, 'vn': {'VP', 'VA', 'AT'},
    'vp': {'VA', 'AT'}, 'va': {'AT'}, 'at': set(), 'vi': set(), 'ed': set(),
}


def _perimetre_valide(monde, role):
    return {'PR': {}, 'VN': {}, 'VP': {'coordination': monde['P']}, 'VA': {'antenne': monde['A']}, 'AT': {'antenne': monde['A']},
            'VI': {}, 'ED': {}, 'SU': {}}[role]


@pytest.mark.parametrize('auteur', sorted(CHOIX))
@pytest.mark.parametrize('role', ['SU', 'PR', 'VN', 'VP', 'VA', 'AT', 'VI', 'ED'])
def test_F02_2e_anti_escalade_service_nommer(monde, auteur, role):
    membre = monde['m']['actif_a']
    compte = monde['comptes'][auteur]
    if role in ('VI', 'ED'):  # les rôles sans fiche se créent par le compte externe, mais nommer() les accepte aussi pour un membre
        pass
    attendu = role in CHOIX[auteur]
    try:
        noms.nommer(compte, membre, role, **_perimetre_valide(monde, role))
        accepte = True
    except noms.ErreurNomination:
        accepte = False
    assert accepte == attendu, (auteur, role)
    assert Nomination.objects.filter(membre=membre, role=role).exists() == attendu
    assert not Nomination.objects.filter(role='SU', membre=membre).exists()


@pytest.mark.parametrize('auteur, role', [('vp', 'VP'), ('vp', 'VN'), ('vp', 'PR'), ('va', 'VA'), ('va', 'VP'), ('pr', 'PR'),
                                          ('pr', 'ED'), ('vn', 'VN'), ('su', 'SU'), ('pr', 'SU'), ('vp', 'SU')])
def test_F02_2e_anti_escalade_formulaire_forge_403_sans_effet(client, monde, auteur, role):
    client.force_login(monde['comptes'][auteur])
    donnees = {'membre': monde['m']['actif_a'].id, 'role': role, 'antenne': monde['A'].id}
    avant = (Nomination.objects.count(), Compte.objects.count())
    assert client.post(reverse('utilisateurs-nommer'), donnees).status_code == 403
    assert (Nomination.objects.count(), Compte.objects.count()) == avant


def test_F02_2e_anti_escalade_changement_de_role_vers_un_role_superieur_ou_egal_refuse(client, monde):
    cible = monde['comptes']['at']
    for auteur, role in (('va', 'VA'), ('va', 'VP'), ('vp', 'VP'), ('vp', 'VN'), ('pr', 'PR'), ('pr', 'ED')):
        client.force_login(monde['comptes'][auteur])
        r = client.post(reverse('utilisateurs-role', kwargs={'id': cible.id}),
                        {'role': role, 'antenne': monde['A'].id, 'coordination': monde['P'].id if role == 'VP' else ''})
        assert r.status_code == 403, (auteur, role)
    assert Nomination.objects.get(compte=cible, active=True).role == 'AT'


def test_F02_2e_anti_escalade_gerer_un_pair_ou_un_superieur_refuse(client, monde):
    c = monde['comptes']
    cas = [('va', 'vp'), ('va', 'va'), ('vp', 'vn'), ('vp', 'pr'), ('vp', 'vp'), ('vn', 'pr'), ('vn', 'vn'), ('pr', 'pr')]
    for auteur, cible in cas:
        client.force_login(c[auteur])
        for route in ('utilisateurs-reinitialiser', 'utilisateurs-desactiver'):
            r = client.post(reverse(route, kwargs={'id': c[cible].id}), {'motif': 'x'})
            assert r.status_code in (403, 404), (auteur, cible, route, r.status_code)
    assert all(Compte.objects.get(pk=c[k].pk).is_active for k in ('vp', 'pr', 'vn', 'va'))


def test_F02_2e_anti_escalade_nomination_hors_de_son_perimetre(client, monde):
    """Un VP de P ne nomme ni dans la coordination Q ni un membre de Q ; un VA ne nomme que dans son antenne."""
    client.force_login(monde['comptes']['vp'])
    assert client.post(reverse('utilisateurs-nommer'), {'membre': monde['m']['actif_q'].id, 'role': 'AT',
                                                         'antenne': monde['AQ'].id}).status_code == 404
    assert client.post(reverse('utilisateurs-nommer'), {'membre': monde['m']['actif_a'].id, 'role': 'AT',
                                                         'antenne': monde['AQ'].id}).status_code == 404
    client.force_login(monde['comptes']['va'])
    assert client.post(reverse('utilisateurs-nommer'), {'membre': monde['m']['actif_a2'].id, 'role': 'AT',
                                                         'antenne': monde['A2'].id}).status_code == 404
    assert not Nomination.objects.filter(membre__in=[monde['m']['actif_q'], monde['m']['actif_a2']]).exists()


def test_F02_2e_anti_escalade_personne_ne_se_nomme_ni_ne_se_promeut(client, monde):
    for profil in ('va', 'vp', 'pr', 'su'):
        client.force_login(monde['comptes'][profil])
        moi = monde['comptes'][profil]
        r = client.post(reverse('utilisateurs-role', kwargs={'id': moi.id}), {'role': 'AT', 'antenne': monde['A'].id})
        assert r.status_code == 403
    # une nomination ne se crée pas pour un compte qui en a déjà une : changer le rôle au lieu d'en empiler une seconde
    membre_va = Membre.objects.create(nom='Membre du VA', antenne=monde['A'], province=monde['P'], is_validate3=True)
    Compte.objects.filter(username='va').update(membreId=membre_va.id)
    client.force_login(monde['comptes']['pr'])
    r = client.post(reverse('utilisateurs-nommer'), {'membre': membre_va.id, 'role': 'VN'})
    assert r.status_code == 422 and Nomination.objects.filter(compte__username='va', active=True).count() == 1


def test_F02_2e_un_compte_su_ne_se_nomme_pas(client, monde):
    membre_su = monde['m']['actif_a']
    Compte.objects.filter(pk=monde['comptes']['su'].pk).update(membreId=membre_su.id)
    client.force_login(monde['comptes']['pr'])
    r = client.post(reverse('utilisateurs-nommer'), {'membre': membre_su.id, 'role': 'AT', 'antenne': monde['A'].id})
    assert r.status_code == 422 and Nomination.objects.filter(compte=monde['comptes']['su'], role='AT').count() == 0


def test_F02_2e_anti_escalade_ancien_nominateur_retrograde_ne_gere_plus_son_ancien_subordonne(client, monde):
    pr = monde['comptes']['pr']
    vn_cible = Compte.objects.create_user('vn-du-pr', password='x')
    creer_nomination(pr, vn_cible, roles.VN)  # nommé par le PR : légitime
    su = Client()
    su.force_login(monde['comptes']['su'])
    r = su.post(reverse('utilisateurs-role', kwargs={'id': pr.id}), {'role': 'VA', 'antenne': monde['A'].id})
    assert r.status_code in (200, 204)
    assert Nomination.objects.get(compte=pr, active=True).role == 'VA'  # le PR est maintenant un simple validateur d'antenne
    client.force_login(Compte.objects.get(pk=pr.pk))
    avant = Compte.objects.get(pk=vn_cible.pk).password
    r = client.post(reverse('utilisateurs-reinitialiser', kwargs={'id': vn_cible.id}))
    assert r.status_code in (403, 404)
    assert Compte.objects.get(pk=vn_cible.pk).password == avant


# ================================================================ 5. SU valide ses saisies ; les autres rôles non

@pytest.mark.parametrize('profil', ['pr', 'vn', 'vp', 'va'])
def test_F02_2e_personne_hors_su_ne_valide_ses_propres_saisies_ni_sa_fiche(client, monde, profil):
    c = monde['comptes'][profil]
    saisie = Membre.objects.create(nom='Ma saisie', antenne=monde['A'], province=monde['P'], user=c, is_validate1=True)
    fiche = Membre.objects.create(nom='Ma fiche', antenne=monde['A'], province=monde['P'], is_validate1=True)
    Compte.objects.filter(pk=c.pk).update(membreId=fiche.id)
    c = Compte.objects.get(pk=c.pk)
    for m in (saisie, fiche):
        assert etapes_a_valider(c, m) == [] and not droits_membre(c, m)['peut_valider'], (profil, m.nom)
    client.force_login(c)
    for m in (saisie, fiche):
        client.post(reverse('validate', kwargs={'id': m.id}))
        m.refresh_from_db()
        assert not m.is_validate2 and not m.is_validate3, (profil, m.nom)


def test_F02_2e_le_su_valide_ses_propres_saisies(client, monde):
    su = monde['comptes']['su']
    saisie = Membre.objects.create(nom='Saisie du SU', antenne=monde['A'], province=monde['P'], user=su, is_validate1=True)
    assert droits_membre(su, saisie)['peut_valider'] and etapes_a_valider(su, saisie)
    client.force_login(su)
    client.post(reverse('validate', kwargs={'id': saisie.id}))
    saisie.refresh_from_db()
    assert saisie.is_validate2 or saisie.is_validate3


def test_F02_2e_les_autres_membres_restent_validables_par_leur_role(monde):
    c = monde['comptes']
    m = monde['m']['saisi_a']
    assert etapes_a_valider(c['va'], m) == ['valide_antenne']
    assert etapes_a_valider(c['pr'], m) == ['valide_antenne', 'valide_province', 'actif']
    assert etapes_a_valider(c['vn'], m) == []  # VN : étape nationale, après l'antenne et la province
    assert etapes_a_valider(c['vp'], m) == []  # VP : étape province, après l'antenne
    for profil in ('at', 'vi', 'ed', 'vi_a'):
        assert etapes_a_valider(c[profil], m) == [], profil
    assert etapes_a_valider(c['vp'], monde['m']['v2_a']) == ['valide_province']  # validé antenne : c'est au tour du VP


# ================================================================ 6. visiteur : membres actifs seulement

@pytest.mark.parametrize('profil, attendus', [
    ('vi', ['Actif A', 'Actif A2', 'Actif Q']),
    ('vi_p', ['Actif A', 'Actif A2']),
    ('vi_a', ['Actif A']),
])
def test_F02_2e_visiteur_voit_les_membres_actifs_de_son_perimetre_seulement(client, monde, profil, attendus):
    c = monde['comptes'][profil]
    assert _noms(membres_du_perimetre(c)) == attendus
    client.force_login(c)
    page = client.get(reverse('liste-membre')).content.decode()
    for nom in ('Saisi A', 'Valide 2 A', 'Saisi Q'):
        assert nom not in page, (profil, nom)
    for nom in attendus:
        assert nom in page, (profil, nom)
    for non_actif in ('saisi_a', 'v2_a', 'saisi_q'):
        assert client.get(reverse('membre-view', kwargs={'id': monde['m'][non_actif].id})).status_code == 404


def test_F02_2e_visiteur_lecture_seule_aucune_ecriture_ni_piece(client, monde):
    client.force_login(monde['comptes']['vi'])
    m = monde['m']['actif_a']
    droits = droits_membre(monde['comptes']['vi'], m)
    assert not any(droits.values())
    for route in ('delete-membre', 'validate'):
        assert client.post(reverse(route, kwargs={'id': m.id}), {'action': 'demander', 'motif': 'x'}).status_code in (403, 404)
    m.refresh_from_db()
    assert not m.suppression_demandee


# ================================================================ 7. nomination échue reste valable

def test_F02_2e_nomination_echue_reste_valable_partout(client, monde):
    va = monde['comptes']['va']
    Nomination.objects.filter(compte=va, active=True).update(debut=date(2015, 1, 1), fin=date(2018, 1, 1))
    va = Compte.objects.get(pk=va.pk)
    assert profil_de(va).mode == 'nomination' and profil_de(va).role == 'VA'
    assert 'Actif A' in _noms(membres_du_perimetre(va))
    assert etapes_a_valider(va, monde['m']['saisi_a']) == ['valide_antenne']
    client.force_login(va)
    assert client.get(reverse('liste-membre')).status_code == 200
    assert client.get(reverse('utilisateurs')).status_code == 200
    assert 'Actif A' in client.get(reverse('liste-membre')).content.decode()


def test_F02_2e_nomination_echue_apparait_dans_les_mandats_a_traiter_sans_perdre_ses_droits(client, monde):
    pr = monde['comptes']['pr']
    Nomination.objects.filter(compte=monde['comptes']['vp'], active=True).update(fin=date.today() - timedelta(days=40))
    client.force_login(pr)
    frag = client.get(reverse('utilisateurs'), {'zone': 'mandats'}, HTTP_HX_REQUEST='true').content.decode()
    assert 'vp' in frag and '<html' not in frag
    assert Compte.objects.get(username='vp').is_active
    assert profil_de(Compte.objects.get(username='vp')).role == 'VP'


def test_F02_2e_nomination_terminee_perd_ses_droits_mais_reste_au_dossier(monde):
    va = monde['comptes']['va']
    noms.terminer(monde['comptes']['su'], va, 'Fin de mandat')
    va = Compte.objects.get(pk=va.pk)
    assert profil_de(va).mode == 'herite' and not droits_membre(va, monde['m']['actif_a'])['peut_valider']
    assert Nomination.objects.filter(compte=va, active=False, motif_fin='Fin de mandat').exists()


# ================================================================ 8. commandes

def _sortie(*args, **kw):
    s = io.StringIO()
    call_command(*args, stdout=s, **kw)
    return s.getvalue()


def test_F02_2e_attribuer_roles_initiaux_dry_run_ne_cree_rien(monde):
    avant = Nomination.objects.count()
    sortie = _sortie('attribuer_roles_initiaux', '--su', 'admin-test', '--dry-run')
    assert 'Simulation' in sortie and Nomination.objects.count() == avant
    assert not Nomination.objects.filter(compte=monde['comptes']['su'], role='SU').exists()


def test_F02_2e_attribuer_roles_initiaux_seul_le_compte_designe_et_idempotent(monde):
    avant_autres = Nomination.objects.exclude(compte=monde['comptes']['su']).count()
    Compte.objects.create_user('sans-role', password='x', privilege5=True)
    sortie = _sortie('attribuer_roles_initiaux', '--su', 'admin-test')
    assert 'créée' in sortie and 'sans-role' in sortie
    assert Nomination.objects.filter(compte=monde['comptes']['su'], role='SU', active=True).count() == 1
    assert Nomination.objects.exclude(compte=monde['comptes']['su']).count() == avant_autres  # aucun autre rôle attribué
    assert not Nomination.objects.filter(compte__username='sans-role').exists()
    total = Nomination.objects.count()
    journal = JournalAction.objects.count()
    assert 'rien à faire' in _sortie('attribuer_roles_initiaux', '--su', 'admin-test')
    _sortie('attribuer_roles_initiaux', '--su', 'admin-test')
    assert Nomination.objects.count() == total and JournalAction.objects.count() == journal


@pytest.mark.parametrize('pseudo', ['personne', 'pr', 'at', ''])
def test_F02_2e_attribuer_roles_initiaux_refuse_un_compte_non_su(monde, pseudo):
    avant = Nomination.objects.count()
    with pytest.raises(CommandError):
        call_command('attribuer_roles_initiaux', '--su', pseudo)
    assert Nomination.objects.count() == avant


def test_F02_2e_attribuer_roles_initiaux_refuse_un_su_inactif(monde):
    s = Compte.objects.create_superuser('su-inactif', 'a@example.invalid', 'x')
    Compte.objects.filter(pk=s.pk).update(is_active=False)
    with pytest.raises(CommandError):
        call_command('attribuer_roles_initiaux', '--su', 'su-inactif')
    assert not Nomination.objects.filter(compte=s).exists()


def test_F02_2e_attribuer_roles_initiaux_exige_l_option_su():
    with pytest.raises(CommandError):
        call_command('attribuer_roles_initiaux')


@pytest.fixture
def mandats(monde):
    """VP : fin dans 30 jours (à venir) ; VA : échu depuis 10 jours ; AT : fin dans 200 jours (rien) ; PR : sans fin."""
    jour = timezone.localdate()
    c = monde['comptes']
    Nomination.objects.filter(compte=c['vp'], active=True).update(fin=jour + timedelta(days=30))
    Nomination.objects.filter(compte=c['va'], active=True).update(fin=jour - timedelta(days=10))
    Nomination.objects.filter(compte=c['at'], active=True).update(fin=jour + timedelta(days=200))
    Nomination.objects.filter(compte=c['pr'], active=True).update(fin=None)
    return monde


def test_F02_2e_alertes_mandats_dry_run_ne_modifie_rien(mandats):
    avant = (Notification.objects.count(), JournalAction.objects.count(),
             list(Nomination.objects.order_by('pk').values_list('pk', 'alerte_envoyee_le', 'active')))
    sortie = _sortie('alertes_mandats', '--dry-run')
    assert 'Simulation' in sortie and '2 alerte(s)' in sortie
    assert (Notification.objects.count(), JournalAction.objects.count(),
            list(Nomination.objects.order_by('pk').values_list('pk', 'alerte_envoyee_le', 'active'))) == avant


def test_F02_2e_alertes_mandats_envoie_une_fois_et_ne_desactive_rien(mandats):
    c = mandats['comptes']
    sortie = _sortie('alertes_mandats')
    assert '2 alerte(s)' in sortie and 'droits actifs jusqu' in sortie
    assert Notification.objects.filter(titre__icontains='échu').count() == 2  # une pour le VP (bientôt), une pour le VA (échu)
    # celui qui a nommé (le SU) est prévenu
    assert Notification.objects.filter(user=c['su']).count() == 2
    assert all(Compte.objects.get(pk=k.pk).is_active for k in c.values())
    assert Nomination.objects.filter(active=True).count() == Nomination.objects.filter(active=True, compte__in=c.values()).count() == 10
    assert profil_de(Compte.objects.get(pk=c['va'].pk)).role == 'VA'  # l'échu garde ses droits
    # idempotence : même jour, rien de plus
    notifications, journal = Notification.objects.count(), JournalAction.objects.filter(action=JournalAction.Action.ALERTE_MANDAT).count()
    assert '0 alerte(s)' in _sortie('alertes_mandats')
    _sortie('alertes_mandats')
    assert Notification.objects.count() == notifications
    assert JournalAction.objects.filter(action=JournalAction.Action.ALERTE_MANDAT).count() == journal == 2


def test_F02_2e_alertes_mandats_echeance_apres_alerte_des_60_jours(mandats):
    _sortie('alertes_mandats')
    vp = Nomination.objects.get(compte=mandats['comptes']['vp'], active=True)
    assert vp.alerte_envoyee_le is not None
    avant = Notification.objects.count()
    # 31 jours plus tard : l'échéance est atteinte, une seconde alerte part, puis plus rien
    plus_tard = timezone.localdate() + timedelta(days=31)
    rapport = noms.alertes_de_mandat(aujourdhui=plus_tard)
    assert [n.compte.username for n in rapport['envoyees']] == ['vp', 'va'] or 'vp' in [n.compte.username for n in rapport['envoyees']]
    assert Notification.objects.count() > avant
    envoye = Notification.objects.count()
    noms.alertes_de_mandat(aujourdhui=plus_tard)
    assert Notification.objects.count() == envoye


def test_F02_2e_alertes_mandats_nominateur_inactif_les_presidents_sont_prevenus(mandats):
    Compte.objects.filter(pk=mandats['comptes']['su'].pk).update(is_active=False)
    _sortie('alertes_mandats')
    assert Notification.objects.filter(user=mandats['comptes']['pr']).count() == 2
    assert Notification.objects.filter(user=mandats['comptes']['su']).count() == 0


def test_F02_2e_alertes_mandats_option_jours(mandats):
    sortie = _sortie('alertes_mandats', '--dry-run', '--jours', '10')
    assert '1 alerte(s)' in sortie  # seul l'échu : le VP (30 jours) n'est plus dans la fenêtre
    sortie = _sortie('alertes_mandats', '--dry-run', '--jours', '365')
    assert '3 alerte(s)' in sortie


# ================================================================ 9. page complète / fragment, entrées invalides, échappement

def test_F02_2e_liste_page_complete_et_fragments(client, monde):
    client.force_login(monde['comptes']['pr'])
    page = client.get(reverse('utilisateurs'))
    html = page.content.decode()
    assert page.status_code == 200 and '<html' in html and 'Mandats à traiter' in html
    assert 'no-store' in page['Cache-Control'] and 'HX-Request' in page['Vary']
    for zone in ('comptes', 'mandats'):
        frag = client.get(reverse('utilisateurs'), {'zone': zone}, HTTP_HX_REQUEST='true')
        assert frag.status_code == 200 and b'<html' not in frag.content, zone
    # la page demandée en HTMX sans zone : fragment de la liste, jamais la coque complète
    assert b'<html' not in client.get(reverse('utilisateurs'), HTTP_HX_REQUEST='true').content
    assert 'mandats' in client.get(reverse('utilisateurs'), {'onglet': 'mandats'}).content.decode()


@pytest.mark.parametrize('params', [
    {'page': 'abc'}, {'page': '9999'}, {'page': '-1'}, {'etat': 'zzz'}, {'role': '<script>'}, {'role': 'sans'}, {'coordination': 'abc'}, {'mandat': "'; DROP TABLE--"}, {'q': 'x' * 5000}, {'q': '%'}, {'onglet': '<b>'},
    {'zone': 'inconnue'},
])
def test_F02_2e_liste_parametres_invalides_jamais_de_500(client, monde, params):
    client.force_login(monde['comptes']['pr'])
    for entetes in ({}, {'HTTP_HX_REQUEST': 'true'}):
        assert client.get(reverse('utilisateurs'), params, **entetes).status_code == 200


@pytest.mark.parametrize('cle', ['antenne', 'coordination'])
def test_F02_2e_liste_identifiant_geant_pas_de_500(client, monde, cle):
    client.force_login(monde['comptes']['pr'])
    assert client.get(reverse('utilisateurs'), {cle: '99999999999999999999'}).status_code == 200


def test_F02_2e_liste_echappe_les_donnees_saisies(client, monde):
    mechant = '<img src=x onerror=alert(1)>'
    c = Compte.objects.create_user('xss-user', password='x', first_name=mechant)
    creer_nomination(monde['comptes']['su'], c, roles.AT, antenne=monde['A'])
    client.force_login(monde['comptes']['pr'])
    page = client.get(reverse('utilisateurs'), {'q': 'xss-user'}, HTTP_HX_REQUEST='true').content.decode()
    assert 'xss-user' in page and mechant not in page
    page = client.get(reverse('utilisateurs'), {'q': mechant}, HTTP_HX_REQUEST='true').content.decode()
    assert mechant not in page
    page = client.get(reverse('utilisateurs-membres-nommables'), {'q': mechant}).content.decode()
    assert mechant not in page


def test_F02_2e_formulaires_erreurs_422_et_modale_conservee(client, monde):
    client.force_login(monde['comptes']['pr'])
    cible = monde['comptes']['at']
    r = client.post(reverse('utilisateurs-desactiver', kwargs={'id': cible.id}), {'motif': '   '})
    assert r.status_code == 422 and b'<html' not in r.content and Compte.objects.get(pk=cible.pk).is_active
    r = client.post(reverse('utilisateurs-desactiver', kwargs={'id': cible.id}), {'motif': 'x' * 501})
    assert r.status_code == 422 and Compte.objects.get(pk=cible.pk).is_active
    r = client.post(reverse('utilisateurs-nommer'), {'membre': monde['m']['saisi_a'].id, 'role': 'AT', 'antenne': monde['A'].id})
    assert r.status_code == 422  # membre non actif
    assert client.post(reverse('utilisateurs-nommer'), {'role': 'AT'}).status_code == 422  # aucun membre choisi
    for donnees in ({'role': 'AT', 'antenne': monde['A'].id, 'debut': 'pas-une-date'}, {'role': 'AT', 'antenne': 'abc'},
                    {'role': 'AT'}, {'role': 'VP', 'antenne': monde['A'].id}):
        r = client.post(reverse('utilisateurs-nommer'), {'membre': monde['m']['actif_a'].id, **donnees})
        assert r.status_code == 422, donnees
    assert not Nomination.objects.filter(membre=monde['m']['actif_a']).exists()
    assert client.post(reverse('utilisateurs-nommer'), {'membre': monde['m']['actif_a'].id, 'role': 'XX'}).status_code == 403  # rôle inconnu : non nommable
    r = client.post(reverse('utilisateurs-externe'), {'username': '', 'type': 'VI'})
    assert r.status_code == 422
    r = client.post(reverse('utilisateurs-externe'), {'username': 'ok-nom', 'type': 'SU'})
    assert r.status_code == 422 and not Compte.objects.filter(username='ok-nom').exists()


def test_F02_2e_motif_de_desactivation_conserve_au_journal_et_compte_inactif_ne_se_connecte_plus(client, monde):
    client.force_login(monde['comptes']['pr'])
    cible = monde['comptes']['at']
    assert client.post(reverse('utilisateurs-desactiver', kwargs={'id': cible.id}), {'motif': 'Départ'}).status_code == 204
    ligne = JournalAction.objects.get(action=JournalAction.Action.DESACTIVATION_COMPTE)
    assert ligne.motif == 'Départ' and ligne.auteur == monde['comptes']['pr']
    r = Client().post(reverse('application'), {'username': 'at', 'password': 'x'})
    assert r.status_code == 200 and 'incorrect' in r.content.decode()  # pas de session : le compte désactivé ne se connecte plus
    assert Nomination.objects.get(compte=cible, active=True)  # nomination conservée


def test_F02_2e_nommer_refuse_une_fin_avant_le_debut(client, monde):
    """Sonde : une date de fin antérieure au début, ou bien au-delà de la durée de la charte, est-elle acceptée ? (documenté)"""
    client.force_login(monde['comptes']['pr'])
    r = client.post(reverse('utilisateurs-nommer'), {'membre': monde['m']['actif_a'].id, 'role': 'AT', 'antenne': monde['A'].id,
                                                    'debut': '01/01/2026', 'fin': '01/01/2020'})
    nomination = Nomination.objects.filter(membre=monde['m']['actif_a']).first()
    assert nomination is None or nomination.fin >= nomination.debut, (r.status_code, nomination and (nomination.debut, nomination.fin))


def test_F02_2e_nommer_fin_au_dela_de_la_duree_de_la_charte(client, monde):
    client.force_login(monde['comptes']['pr'])
    client.post(reverse('utilisateurs-nommer'), {'membre': monde['m']['actif_a'].id, 'role': 'AT', 'antenne': monde['A'].id,
                                                'debut': '01/01/2026', 'fin': '01/01/2060'})
    nomination = Nomination.objects.filter(membre=monde['m']['actif_a']).first()
    assert nomination is None or (nomination.fin - nomination.debut).days <= 3 * 366


def test_F02_2e_service_fin_de_mandat_bornee_par_la_charte(monde):
    from datetime import date
    su = monde['comptes']['su']
    for role, ans, kw in (('AT', 3, {'antenne': monde['A']}), ('VP', 4, {'coordination': monde['P']}) if 'P' in monde else ('AT', 3, {'antenne': monde['A']})):
        cible = Compte.objects.create_user(f'borne-{role}-{ans}', password='x')
        debut = date(2026, 1, 1)
        with pytest.raises(noms.RegleMetier):
            creer_nomination_verifiee(su, cible, role, kw, debut, date(2025, 12, 31))
        with pytest.raises(noms.RegleMetier):
            creer_nomination_verifiee(su, cible, role, kw, debut, date(2026 + ans, 1, 2))
        assert creer_nomination_verifiee(su, cible, role, kw, debut, date(2026 + ans, 1, 1)).fin == date(2026 + ans, 1, 1)


def creer_nomination_verifiee(auteur, cible, role, kw, debut, fin):
    return creer_nomination(auteur, cible, role, debut=debut, fin=fin, **kw)
