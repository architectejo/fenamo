"""Commande charger_donnees_demo : refus hors DEBUG, chargement par les vrais services, idempotence, réinitialisation ciblée."""
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from compte.models import Compte, JournalAction, Nomination
from coptapp.models import Antenne, Membre, Moto, Notification, Province
from tests.test_plan_url import hachage_rapide  # noqa: F401


def _lancer(*args):
    call_command('charger_donnees_demo', *args, verbosity=0)


@pytest.mark.django_db
def test_F02_demo_refuse_hors_debug(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        _lancer()
    assert not Compte.objects.filter(username__startswith='demo.').exists()


@pytest.mark.django_db
def test_F02_demo_charge_les_roles_les_etats_et_le_journal(settings):
    settings.DEBUG = True
    _lancer('--mot-de-passe', 'Secret-Demo-1')
    assert {n.role for n in Nomination.objects.filter(active=True, compte__username__startswith='demo.')} == {'PR', 'VN', 'VP', 'VA', 'AT', 'VI', 'ED'}
    su = Compte.objects.get(username='demo.su')
    assert su.is_superuser and su.check_password('Secret-Demo-1')
    assert Compte.objects.get(username='demo.at').check_password('Secret-Demo-1')
    assert Antenne.objects.filter(code__startswith='DEMO').count() == 6
    assert Province.objects.filter(antennes__code__startswith='DEMO').distinct().count() == 3
    membres = Membre.objects.filter(idf__startswith='DEMO')
    assert membres.count() >= 40
    assert membres.filter(is_validate2=False, is_validate3=False, suppression_demandee=False).exists()  # saisi
    assert membres.filter(is_validate2=True, is_validate3=False, is_delete=False).exists()  # validé antenne / renvoyé
    assert membres.filter(is_validate3=True, is_delete=False).exists()  # actif
    assert membres.filter(suppression_demandee=True).exists() and membres.filter(is_delete=True).exists()
    assert membres.filter(renvoye=True).count() == 2 and Notification.objects.filter(titre__startswith='Fiche renvoyée').count() == 2
    assert Moto.objects.filter(num_chassie__startswith='DEMO').count() >= 5
    assert Notification.objects.filter(titre__startswith='[DEMO]').count() == 3
    actions = set(JournalAction.objects.values_list('action', flat=True))
    assert {'nomination', 'validation', 'renvoi'} <= actions
    mobile = Membre.objects.get(idf='DEMO-MOB')
    assert mobile.password and mobile.password != 'Secret-Demo-1'  # haché


@pytest.mark.django_db
def test_F02_demo_idempotente_et_reinitialisation_ne_touche_que_la_demo(settings):
    settings.DEBUG = True
    reel = Membre.objects.create(nom='Fiche non démo', idf='MBR0000001')
    _lancer()
    avant = (Compte.objects.filter(username__startswith='demo.').count(), Membre.objects.count(), Moto.objects.count())
    _lancer()  # deuxième passage : rien ne change
    assert (Compte.objects.filter(username__startswith='demo.').count(), Membre.objects.count(), Moto.objects.count()) == avant
    _lancer('--reinitialiser')
    assert (Compte.objects.filter(username__startswith='demo.').count(), Membre.objects.count(), Moto.objects.count()) == avant
    assert Membre.objects.filter(pk=reel.pk).exists()
    assert Province.objects.filter(code__isnull=False).count() == 27
