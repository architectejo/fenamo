"""Revalidation indépendante (testeur) : les boutons du gabarit contre les droits des vues (F-23, F-25, F-35, F-26).

Pour chaque profil et chaque état de fiche, on lit le HTML réellement rendu (fiche d'un membre et liste des membres),
on relève chaque bouton qui déclenche une action (formulaire POST, lien-bouton) puis on REJOUE cette action avec le
même compte : une action affichée ne doit jamais répondre 403, 404 ou 405. Les POST sont rejoués dans un savepoint
annulé (aucun effet durable). Le sens inverse est vérifié sur les liens et sur la modification.
"""
import re
from html.parser import HTMLParser

import pytest
from django.db import transaction
from django.urls import reverse

from compte.models import Compte
from coptapp.models import Famille, Membre, Moto
from tests.test_F21_matrice_routes import PROFILS, acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

REFUS = (403, 404, 405)


# ---------------------------------------------------------------- lecture du HTML rendu

class Releveur(HTMLParser):
    """Relève les formulaires POST (action, champs) et les liens-boutons (a.bouton, a.bouton-icone)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.formulaires, self.liens = [], []
        self._form = None
        self._textarea = None

    def handle_starttag(self, balise, attrs):
        a = dict(attrs)
        if balise == 'form' and (a.get('method') or 'get').lower() == 'post':
            self._form = {'action': a.get('action'), 'champs': {}, 'envois': []}
            self.formulaires.append(self._form)
        elif balise == 'a' and a.get('href') and 'bouton' in (a.get('class') or ''):
            self.liens.append(a['href'])
        elif self._form is not None:
            nom = a.get('name')
            if balise == 'input' and nom and a.get('type') != 'file' and a.get('type') not in ('checkbox', 'radio'):
                self._form['champs'][nom] = a.get('value', '')
            elif balise == 'input' and nom and a.get('type') in ('checkbox', 'radio') and 'checked' in a:
                self._form['champs'][nom] = a.get('value', 'on')
            elif balise == 'textarea' and nom:
                self._form['champs'][nom] = ''
                self._textarea = nom
            elif balise == 'select' and nom:
                self._form['champs'].setdefault(nom, '')
            elif balise == 'option' and a.get('value') and self._form['champs'].get(self._dernier_select(), None) == '':
                self._form['champs'][self._dernier_select()] = a['value']
            elif balise == 'button' and a.get('type') == 'submit' and nom:
                self._form['envois'].append((nom, a.get('value', '')))

    def _dernier_select(self):
        return next((n for n, v in reversed(list(self._form['champs'].items()))), None)

    def handle_data(self, donnees):
        if self._textarea and self._form is not None:
            self._form['champs'][self._textarea] += donnees

    def handle_endtag(self, balise):
        if balise == 'textarea':
            self._textarea = None
        elif balise == 'form':
            self._form = None


def releve(html):
    r = Releveur()
    r.feed(html)
    return r


def charge_utile(formulaire, envoi=None):
    donnees = dict(formulaire['champs'])
    if 'motif' in donnees and not donnees['motif'].strip():
        donnees['motif'] = 'Motif de test'
    if 'numero' in donnees and not donnees['numero']:
        donnees['numero'] = 'INCONNU'
    if envoi:
        donnees[envoi[0]] = envoi[1]
    return donnees


def rejouer_post(client, url, donnees):
    """POST dans un savepoint annulé ; retourne (statut, photo des drapeaux d'états du membre ciblé ou None)."""
    with transaction.atomic():
        reponse = client.post(url, donnees)
        instantane = {m.pk: (m.is_validate1, m.is_validate2, m.is_validate3, m.is_delete, m.suppression_demandee)
                      for m in Membre.objects.all()}
        transaction.set_rollback(True)
    return reponse.status_code, instantane


# ---------------------------------------------------------------- jeux d'essai

ETATS_FICHE = {
    'normal': {},
    'demande_par_p1': {'suppression_demandee': True, 'motif_suppression': 'Doublon'},
    'supprime': {'is_delete': True, 'motif_suppression': 'Décès'},
    'actif': {'is_validate3': True},
    'avant_v1': {'is_validate2': False},
}


def _preparer(acteurs, etat):
    membre = acteurs['membre']
    for champ, valeur in ETATS_FICHE[etat].items():
        setattr(membre, champ, valeur)
    if membre.suppression_demandee:
        membre.suppression_demandee_par = acteurs['comptes']['p1']
    membre.qualite = 'MOTARD ET PROPRIETAIRE'
    membre.save()
    Moto.objects.filter(pk=acteurs['moto'].pk).update(motard_id=str(membre.pk))
    Famille.objects.get_or_create(membre=membre, beneficiere='Proche fictif')
    return membre


# ---------------------------------------------------------------- la fiche

BUG_FICHE_SUPPRIMEE = pytest.mark.xfail(strict=False, reason=(
    "BUG a corriger (frontend-htmx / backend-django) : sur la fiche d'un membre SUPPRIME, les boutons engins et famille "
    "(ajouter, modifier, supprimer, attribuer) restent affiches alors que les vues repondent 404 (membre hors perimetre)."))
ETATS_A_REJOUER = [pytest.param(e, marks=BUG_FICHE_SUPPRIMEE) if e == 'supprime' else e for e in ETATS_FICHE]


@pytest.mark.parametrize('etat', ETATS_A_REJOUER)
@pytest.mark.parametrize('profil', PROFILS)
def test_F23_aucun_bouton_de_la_fiche_dont_la_vue_repond_refus(client, acteurs, profil, etat):
    membre = _preparer(acteurs, etat)
    client.raise_request_exception = False
    client.force_login(acteurs['comptes'][profil])
    url_fiche = reverse('membre-view', kwargs={'id': membre.id})
    reponse = client.get(url_fiche)
    if reponse.status_code != 200:
        return  # fiche hors périmètre : aucun bouton
    page = releve(reponse.content.decode())
    incoherences = []
    for form in page.formulaires:
        action = form['action'] or url_fiche
        if action.rstrip('/') in (reverse('deconnexion').rstrip('/'), reverse('recherche').rstrip('/')):
            continue  # coque : déconnexion et recherche de la barre du haut
        envois = form['envois'] or [None]
        for envoi in envois:
            statut, _ = rejouer_post(client, action, charge_utile(form, envoi))
            if statut in REFUS:
                incoherences.append(f'POST {action} {envoi} -> {statut}')
    for lien in page.liens:
        if lien.startswith('/') and not lien.startswith(('/membres/?', '/connexion')) and lien not in ('/', url_fiche):
            statut = client.get(lien).status_code
            if statut in REFUS:
                incoherences.append(f'GET {lien} -> {statut}')
    assert not incoherences, f'{profil}/{etat} : bouton affiché mais refusé : {incoherences}'


@pytest.mark.parametrize('etat', ['normal', 'avant_v1'])
@pytest.mark.parametrize('profil', PROFILS)
def test_F23_sens_inverse_liens_et_modification_absents_seulement_si_refuses(client, acteurs, profil, etat):
    """Un lien d'action ou la modification que la vue autoriserait doit être affiché (pas de droit caché)."""
    membre = _preparer(acteurs, etat)
    client.raise_request_exception = False
    client.force_login(acteurs['comptes'][profil])
    url_fiche = reverse('membre-view', kwargs={'id': membre.id})
    reponse = client.get(url_fiche)
    if reponse.status_code != 200:
        return
    page = releve(reponse.content.decode())
    affiches = set(page.liens)
    candidats = {
        reverse('add-moto', kwargs={'id': membre.id}): 'ajouter un engin',
        reverse('add-family', kwargs={'id': membre.id}): 'ajouter un proche',
        reverse('edit-moto', kwargs={'id': acteurs['moto'].id}): 'modifier un engin',
        reverse('edit-family', kwargs={'id': acteurs['famille'].id}): 'modifier un proche',
    }
    manquants = [nom for lien, nom in candidats.items() if client.get(lien).status_code == 200 and lien not in affiches]
    assert not manquants, f'{profil}/{etat} : action permise par la vue mais sans bouton : {manquants}'
    # modification : bouton « Modifier » <=> la vue accepte le POST « modifier »
    with transaction.atomic():
        statut = client.post(url_fiche, {'modifier': '1', 'nom': membre.nom, 'date': '01-01-1990'}).status_code
        transaction.set_rollback(True)
    assert (statut != 403) == ('id="modale-modifier"' in reponse.content.decode()), f'{profil}/{etat} modifier {statut}'


# ---------------------------------------------------------------- la liste

@pytest.fixture
def membres_de_la_liste(acteurs):
    """Trois membres de l'association aux trois états : saisi, validé antenne, actif."""
    base = dict(structure=acteurs['association'], province=acteurs['province'], antenne=acteurs['antenne'])
    return {
        'saisi': Membre.objects.create(nom='Liste Saisi', **base),
        'valide_antenne': Membre.objects.create(nom='Liste Antenne', is_validate2=True, **base),
        'actif': Membre.objects.create(nom='Liste Actif', is_validate2=True, is_validate3=True, **base),
        'saisie_de_p2': Membre.objects.create(nom='Liste Saisie P2', user=acteurs['comptes']['p2'], **base),
    }


@pytest.mark.parametrize('profil', PROFILS)
def test_F23_boutons_valider_de_la_liste_correspondent_a_la_vue(client, acteurs, membres_de_la_liste, profil):
    """Chaque bouton « Valider » affiché, rejoué, pose réellement une étape ; il est absent si la vue ne ferait rien."""
    client.raise_request_exception = False
    client.force_login(acteurs['comptes'][profil])
    reponse = client.get(reverse('liste-membre'))
    assert reponse.status_code == 200
    page = releve(reponse.content.decode())
    url_valider = {reverse('validate', kwargs={'id': m.id}): m for m in Membre.objects.all()}
    affiches = {f['action'] for f in page.formulaires if f['action'] in url_valider}
    for action in affiches:
        membre = url_valider[action]
        form = next(f for f in page.formulaires if f['action'] == action)
        statut, instantane = rejouer_post(client, action, charge_utile(form))
        assert statut not in REFUS, f'{profil} {membre.nom} : bouton Valider -> {statut}'
        avant = (membre.is_validate1, membre.is_validate2, membre.is_validate3)
        apres = instantane[membre.pk][:3]
        assert apres != avant, f'{profil} {membre.nom} : bouton Valider affiché mais la vue ne valide rien'
    # sens inverse : la vue valide (drapeaux modifiés) => le bouton est affiché
    for action, membre in url_valider.items():
        if membre.nom is None or membre.pk not in {m.pk for m in page_membres(client, reponse)}:
            continue
        statut, instantane = rejouer_post(client, action, {})
        if statut == 302 and instantane[membre.pk][:3] != (membre.is_validate1, membre.is_validate2, membre.is_validate3):
            assert action in affiches, f'{profil} {membre.nom} : validation possible sans bouton'


def page_membres(client, reponse):
    """Membres présents sur la page de liste (d'après le contexte)."""
    return list(reponse.context['page_obj'])


@pytest.mark.parametrize('profil', PROFILS)
def test_F23_liste_ne_montre_pas_de_bouton_d_ecriture_hors_valider(client, acteurs, membres_de_la_liste, profil):
    """La liste n'expose que « Valider » : aucun formulaire POST vers autre chose (suppression, rattachement…)."""
    client.force_login(acteurs['comptes'][profil])
    page = releve(client.get(reverse('liste-membre')).content.decode())
    autres = [f['action'] for f in page.formulaires
              if f['action'] and not re.fullmatch(r'/membres/\d+/valider/', f['action']) and f['action'] not in ('/deconnexion/', '/recherche/')]
    assert not autres, autres
