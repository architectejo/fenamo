"""Services d'indicateurs du tableau de bord et d'historique d'un objet."""
from compte.models import Compte, JournalAction
from compte.services.journal import journaliser
from coptapp.models import Membre
from coptapp.services.historique import historique_objet
from coptapp.services.tableau_bord import indicateurs_tableau_bord, membres_du_perimetre
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def _membres(jeu):
    base = dict(province=jeu['province'], ville=jeu['ville'], antenne=jeu['antenne'], structure=jeu['association'])
    from datetime import date
    Membre.objects.create(nom='Valide A', date_naissance=date(1990, 1, 1), etat='valide_antenne', **base)
    Membre.objects.create(nom='Actif', date_naissance=date(1990, 1, 1), etat='actif', **base)
    Membre.objects.create(nom='Supprime', date_naissance=date(1990, 1, 1), etat='supprime', **base)


def test_F28_indicateurs_comptent_par_etat(jeu):
    _membres(jeu)
    ind = indicateurs_tableau_bord(jeu['compte'])
    assert (ind['saisis'], ind['valides_antenne'], ind['actifs'], ind['valides_province'], ind['renvoyes']) == (1, 1, 1, 0, 0)  # le membre du jeu est « saisi »
    assert ind['en_attente_total'] == 2 and ind['engins'] == 1 and ind['associations'] == 1
    assert ind['graphique']['valeurs'] == [1, 1, 0, 1, 0]
    assert ind['graphique']['libelles'] == ['Saisi', 'Validé antenne', 'Validé province', 'Actif', 'Renvoyé']
    assert [m.nom for m in ind['en_attente']] and all(m.etat != 'actif' for m in ind['en_attente'])


def test_F28_perimetre_des_indicateurs_suit_les_privileges(jeu):
    _membres(jeu)
    assert membres_du_perimetre(jeu['compte']).count() == 3
    p4 = Compte.objects.create_user('p4', password='x', privilege4=True)
    assert [m.nom for m in membres_du_perimetre(p4)] == ['Actif']
    p3 = Compte.objects.create_user('p3', password='x', privilege3=True)
    assert {m.nom for m in membres_du_perimetre(p3)} == {'Valide A', 'Actif'}
    sans = Compte.objects.create_user('sans', password='x')
    assert membres_du_perimetre(sans).count() == 0  # sans privilège : rien (jamais « tout »), comme la liste héritée


def test_F28_historique_objet(jeu):
    for i in range(3):
        journaliser(jeu['compte'], JournalAction.Action.VALIDATION, jeu['membre'], motif=f'm{i}')
    journaliser(jeu['compte'], JournalAction.Action.VALIDATION, jeu['moto'])
    lignes = historique_objet(jeu['membre'])
    assert [ligne.motif for ligne in lignes] == ['m2', 'm1', 'm0']
    assert len(historique_objet(jeu['membre'], limite=2)) == 2
    assert len(historique_objet(jeu['moto'])) == 1
    assert historique_objet(None) == [] and historique_objet(Membre()) == []
