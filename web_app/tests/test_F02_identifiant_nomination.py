"""F-02 (dérogation décidée par l'utilisateur, docs/decisions.md) : identifiant et mot de passe initial « prenom[nombre]@fenamordc.hub » à la
nomination d'un membre ; garde-fous (changement forcé, rien d'autre accessible, jamais journalisé, F-03 et F-05 inchangés)."""
import re

import pytest
from django.urls import reverse

from compte import roles
from compte.models import Compte, JournalAction
from compte.services import comptes as C
from compte.services import nominations as N
from compte.services.nominations import RegleMetier
from coptapp.models import Membre
from tests.test_F02_droits_roles import _compte, _nommer, acteurs_roles, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

FORMAT = re.compile(r'^[a-z0-9]+[1-9][0-9]{3}@fenamordc\.hub$')


def _actif(monde, nom):
    return Membre.objects.create(nom=nom, antenne=monde['antenne_p'], province=monde['P'], etat='actif')


@pytest.fixture
def va(monde):
    return _nommer(monde, roles.VA, antenne=monde['antenne_p'])


@pytest.mark.parametrize('nom, prenom', [('Jean-Pierre Kabongo', 'jeanpierre'), ('Élise Mukendi', 'elise'), ("N'Golo Kanté", 'ngolo'),
                                         ('  Ève  ', 'eve'), ('Cœur Brisé', 'coeur'), ('François', 'francois'), ('José-Luis', 'joseluis'),
                                         ('', 'membre'), (None, 'membre'), ('123', '123'), ('---', 'membre'), ('Müller Hans', 'muller')])
def test_F02_translitteration_du_prenom(nom, prenom):
    assert C.prenom_ascii(nom) == prenom


def test_F02_nomination_cree_identifiant_et_mot_de_passe_identiques(monde, va):
    membre = _actif(monde, 'Jean-Pierre Kabongo')
    nomination, mot_de_passe = N.nommer(va, membre, roles.AT, antenne=monde['antenne_p'])
    compte = nomination.compte
    assert FORMAT.match(compte.username) and compte.username.startswith('jeanpierre') and mot_de_passe == compte.username
    assert compte.check_password(mot_de_passe) and compte.doit_changer_mot_de_passe and compte.membreId == membre.pk
    assert 1000 <= int(re.search(r'(\d{4})@', compte.username).group(1)) <= 9999


def test_F02_unicite_sans_tenir_compte_de_la_casse_et_collision(monde, va, monkeypatch):
    tirages = iter([1234, 1234, 1234, 5678])  # trois collisions (casse différente comprise), puis un nombre libre
    monkeypatch.setattr(C.secrets, 'randbelow', lambda n: next(tirages) - 1000)
    _compte('Elise1234@FENAMORDC.HUB')
    compte = N.nommer(va, _actif(monde, 'Élise'), roles.AT, antenne=monde['antenne_p'])[0].compte
    assert compte.username == 'elise5678@fenamordc.hub'


def test_F02_collision_persistante_leve_une_regle_metier_explicite(monde, va, monkeypatch):
    monkeypatch.setattr(C.secrets, 'randbelow', lambda n: 0)
    _compte('paul1000@fenamordc.hub')
    with pytest.raises(RegleMetier):
        N.nommer(va, _actif(monde, 'Paul'), roles.AT, antenne=monde['antenne_p'])
    assert not Compte.objects.filter(username__startswith='paul', membreId__isnull=False).exists()  # rien de créé


def test_F02_le_nombre_est_aleatoire_pas_sequentiel(monde, va):
    nombres = []
    for i in range(12):
        compte = N.nommer(va, _actif(monde, f'Prénom{i}'), roles.AT, antenne=monde['antenne_p'])[0].compte
        nombres.append(int(re.search(r'(\d{4})@', compte.username).group(1)))
    assert len(set(nombres)) > 6 and nombres != sorted(nombres) and nombres != list(range(nombres[0], nombres[0] + 12))


def test_F02_la_source_du_hasard_est_secrets():
    import inspect
    assert 'secrets.randbelow' in inspect.getsource(C.identifiant_de_nomination) and 'random.' not in inspect.getsource(C)


def test_F02_membre_deja_titulaire_d_un_compte_garde_ses_identifiants(monde, va):
    membre = _actif(monde, 'Existant')
    ancien = _compte('ancien-pseudo', membreId=membre.pk)
    ancien.set_password('Mot-de-passe-perso-9')
    ancien.save()
    nomination, mot_de_passe = N.nommer(va, membre, roles.AT, antenne=monde['antenne_p'])
    ancien.refresh_from_db()
    assert mot_de_passe is None and nomination.compte == ancien and ancien.username == 'ancien-pseudo' and ancien.check_password('Mot-de-passe-perso-9')


def test_F03_et_F05_gardent_un_mot_de_passe_aleatoire(monde, acteurs_roles):
    compte, _nomination, mot_de_passe = N.creer_compte_externe(acteurs_roles['PR'], 'visiteur-externe', roles.VI)
    assert len(mot_de_passe) == 12 and '@' not in mot_de_passe and compte.username == 'visiteur-externe'
    cible = acteurs_roles['AT']
    nouveau = N.reinitialiser_mot_de_passe(acteurs_roles['PR'], cible)
    assert len(nouveau) == 12 and not nouveau.endswith('@fenamordc.hub') and nouveau != cible.username


def test_F02_mot_de_passe_jamais_journalise_meme_hache(monde, va):
    nomination, mot_de_passe = N.nommer(va, _actif(monde, 'Secret'), roles.AT, antenne=monde['antenne_p'])
    compte = Compte.objects.get(pk=nomination.compte_id)
    brut = ' '.join(f'{l.avant} {l.apres} {l.motif} {l.objet_libelle}' for l in JournalAction.objects.all())
    assert compte.password not in brut and 'pbkdf2' not in brut and 'md5$' not in brut
    creation = JournalAction.objects.get(action=JournalAction.Action.CREATION_COMPTE, objet_id=compte.pk)
    assert 'password' not in str(creation.apres) and mot_de_passe not in str(creation.apres) + creation.motif
    assert mot_de_passe not in brut and 'secret****@fenamordc.hub' in str(creation.apres) and 'secret****@fenamordc.hub' in brut  # masqué


# ---------------------------------------------------------------- garde-fous : changement forcé

def test_F02_rien_d_autre_accessible_tant_que_le_mot_de_passe_n_est_pas_change(client, monde, va):
    compte = N.nommer(va, _actif(monde, 'Bloque'), roles.AT, antenne=monde['antenne_p'])[0].compte
    client.force_login(Compte.objects.get(pk=compte.pk))
    for adresse in (reverse('tableau-bord'), reverse('liste-membre'), reverse('engin-liste'), reverse('utilisateurs'), '/api/v1/site/config/',
                    '/api/v1/sante/'):
        reponse = client.get(adresse)
        assert reponse.status_code in (302, 403) and (reponse.status_code == 403 or reponse.url == reverse('securite')), adresse
    assert client.get(reverse('securite')).status_code == 200  # la page de changement
    assert client.post(reverse('deconnexion')).status_code == 302 and '_auth_user_id' not in client.session  # la déconnexion reste possible
    assert client.get('/static/css/app.css').status_code != 403


def test_F02_nouveau_mot_de_passe_regles(client, monde, va):
    compte = N.nommer(va, _actif(monde, 'Lucie'), roles.AT, antenne=monde['antenne_p'])[0].compte
    initial = compte.username
    client.force_login(Compte.objects.get(pk=compte.pk))
    url = reverse('securite')

    def essayer(nouveau):
        return client.post(url, {'old_password': initial, 'new_password1': nouveau, 'new_password2': nouveau})

    for refuse in (initial, f'{initial}!', initial.upper(), f'x{compte.username.split("@")[0]}Y9', 'court', '12345678', 'password'):
        reponse = essayer(refuse)
        assert reponse.status_code == 200 and Compte.objects.get(pk=compte.pk).doit_changer_mot_de_passe, refuse  # reste sur le formulaire
    assert essayer('Un-Tout-Nouveau-Secret-83').status_code == 302
    apres = Compte.objects.get(pk=compte.pk)
    assert not apres.doit_changer_mot_de_passe and apres.check_password('Un-Tout-Nouveau-Secret-83') and not apres.check_password(initial)
    assert client.get(reverse('tableau-bord')).status_code in (200, 302)  # plus bloqué par le changement forcé


# ---------------------------------------------------------------- réponse à l'auteur

def test_F02_reponse_unique_no_store_sans_fuite(client, monde, va):
    membre = _actif(monde, 'Hortense')
    client.force_login(va)
    reponse = client.post(reverse('utilisateurs-nommer'), {'membre': membre.pk, 'role': 'AT', 'antenne': monde['antenne_p'].pk},
                          HTTP_HX_REQUEST='true')
    assert reponse.status_code == 200 and 'no-store' in reponse['Cache-Control']
    compte = Compte.objects.get(membreId=membre.pk)
    contexte = reponse.context
    assert contexte['identifiant'] == compte.username == contexte['mot_de_passe_initial'] == contexte['valeur'] and contexte['identifiant_initial'] is True
    assert compte.username in reponse.content.decode()
    fuites = ' '.join([str(reponse.headers.get('HX-Trigger', '')), str(dict(client.session)), ' '.join(str(m) for m in contexte.get('messages', []))])
    assert compte.username not in fuites
    # F-03 : la même modale, avec un mot de passe aléatoire
    externe = client.post(reverse('utilisateurs-externe'), {'username': 'vis-ext', 'role': 'VI'}, HTTP_HX_REQUEST='true')
    assert externe.status_code in (200, 403, 422)


def test_F02_la_liste_masque_l_identifiant_tant_que_le_mot_de_passe_initial_n_est_pas_change(client, monde, va):
    compte = N.nommer(va, _actif(monde, 'Masque'), roles.AT, antenne=monde['antenne_p'])[0].compte
    client.force_login(va)
    page = client.get(reverse('utilisateurs'), {'q': 'masque'}, HTTP_HX_REQUEST='true').content.decode()
    assert compte.username not in page and 'masque****@fenamordc.hub' in page
    Compte.objects.filter(pk=compte.pk).update(doit_changer_mot_de_passe=False)
    assert compte.username in client.get(reverse('utilisateurs'), {'q': 'masque'}, HTTP_HX_REQUEST='true').content.decode()
