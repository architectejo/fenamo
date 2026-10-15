"""F-33 / F-35 : attribuer un motard à un engin exige le droit sur le membre cible ET sur l'engin (son propriétaire)."""
from datetime import date

from django.urls import reverse

from compte.models import Compte
from coptapp.models import AssociationMembre, Membre, Moto
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def _compte(nom, **kw):
    return Compte.objects.create_user(nom, password='x', **kw)


def _attribuer(client, cible, numero):
    return client.post(reverse('moto-attribution', args=[cible.id]), {'numero': numero})


def test_F33_privilege2_ne_rattache_pas_l_engin_d_un_autre_membre(client, jeu):
    p2 = _compte('p2m', privilege2=True)
    jeu['association'].users.add(p2)
    autre_assoc = AssociationMembre.objects.create(nom='Autre', num_justice='F-5')
    etranger = Membre.objects.create(nom='Étranger', etat='valide_antenne', structure=autre_assoc)
    moto = Moto.objects.create(proprietaire=etranger, abonnement=date(2030, 1, 1), numero='900ZZ')
    Membre.objects.filter(pk=jeu['membre'].pk).update(structure=jeu['association'], etat='valide_antenne')
    client.force_login(p2)
    assert _attribuer(client, jeu['membre'], '900ZZ').status_code == 403
    moto.refresh_from_db()
    assert not moto.motard_id


def test_F33_agent_seul_refuse_apres_la_premiere_validation(client, jeu):
    agent = _compte('agentm', privilege1=True)
    membre = Membre.objects.create(nom='Saisie', user=agent, structure=jeu['association'])
    moto = Moto.objects.create(proprietaire=membre, abonnement=date(2030, 1, 1), numero='901AA')
    client.force_login(agent)
    assert _attribuer(client, membre, '901AA').status_code == 302  # avant V1 : permis
    moto.refresh_from_db()
    assert moto.motard_id == str(membre.id)
    Moto.objects.filter(pk=moto.pk).update(motard_id=None)
    Membre.objects.filter(pk=membre.pk).update(etat='valide_antenne')
    assert _attribuer(client, membre, '901AA').status_code == 403
    moto.refresh_from_db()
    assert not moto.motard_id


def test_F33_super_utilisateur_attribue(client, jeu):
    client.force_login(jeu['compte'])
    assert _attribuer(client, jeu['membre'], '001PF').status_code == 302
    jeu['moto'].refresh_from_db()
    assert jeu['moto'].motard_id == str(jeu['membre'].id)


def test_F33_service_attribuer_engin_codes_et_journal(jeu):
    from compte.models import JournalAction
    from coptapp.services.engins import attribuer_engin
    su = jeu['compte']
    assert attribuer_engin(su, jeu['membre'], '  ') == 'numero_requis'
    assert attribuer_engin(su, jeu['membre'], 'INCONNU') == 'introuvable'
    Moto.objects.create(proprietaire=jeu['membre'], abonnement=date(2030, 1, 1), numero='001PF')  # doublon de numéro
    assert attribuer_engin(su, jeu['membre'], '001PF') == 'ambigu'
    Moto.objects.filter(pk=jeu['moto'].pk).update(numero='777QQ')
    assert attribuer_engin(su, jeu['membre'], '777QQ') == 'attribue'
    jeu['moto'].refresh_from_db()
    assert jeu['moto'].motard_id == str(jeu['membre'].id)
    ligne = JournalAction.objects.get(action=JournalAction.Action.RATTACHEMENT)
    assert ligne.avant == {'motard_id': None} and ligne.apres == {'motard_id': str(jeu['membre'].id)}


def test_F33_service_ecrit_par_colonnes(jeu):
    from coptapp.services.engins import attribuer_engin
    Moto.objects.filter(pk=jeu['moto'].pk).update(marque='Concurrente')
    attribuer_engin(jeu['compte'], jeu['membre'], '001PF')
    jeu['moto'].refresh_from_db()
    assert jeu['moto'].marque == 'Concurrente' and jeu['moto'].motard_id
