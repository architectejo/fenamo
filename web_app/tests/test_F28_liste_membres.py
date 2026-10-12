"""F-28 : la liste des membres ne plante pas selon les comptes (sans fiche, ou plusieurs comptes par membre)."""
from django.urls import reverse

from compte.models import Compte
from compte.services.comptes import compte_du_membre
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

MDP = 'Bon-mot-de-passe-1x'


def test_F28_su_sans_fiche_membre_voit_la_liste(client, jeu):
    Compte.objects.filter(pk=jeu['compte'].pk).update(membreId=None)
    Compte.objects.create_user('autre-sans-fiche', password=MDP)  # deuxième compte sans membre
    client.force_login(jeu['compte'])
    r = client.get(reverse('liste-membre'))
    assert r.status_code == 200
    assert 'Membre Fictif' in r.content.decode()


def test_F28_plusieurs_comptes_pour_un_meme_membre(client, jeu):
    Compte.objects.create_user('doublon1', password=MDP, membreId=jeu['membre'].id)
    Compte.objects.create_user('doublon2', password=MDP, membreId=jeu['membre'].id)
    client.force_login(jeu['compte'])
    for nom, kwargs in (('liste-membre', {}), ('membre-view', {'id': jeu['membre'].id}),
                        ('view-moto', {'id': jeu['moto'].id}), ('notifys', {})):
        assert client.get(reverse(nom, kwargs=kwargs)).status_code == 200, nom


def test_F28_compte_du_membre_sur_s_et_none(jeu):
    assert compte_du_membre(None) is None
    assert compte_du_membre(99999) is None
    Compte.objects.filter(pk=jeu['compte'].pk).update(membreId=None)
    premier = Compte.objects.create_user('premier', password=MDP, membreId=jeu['membre'].id)
    Compte.objects.create_user('second', password=MDP, membreId=jeu['membre'].id)
    assert compte_du_membre(jeu['membre'].id) == premier


def test_F28_utilisateur_sans_privilege_ni_fiche_ne_plante_pas(client, db):
    client.force_login(Compte.objects.create_user('nu', password=MDP))
    assert client.get(reverse('liste-membre')).status_code == 200
