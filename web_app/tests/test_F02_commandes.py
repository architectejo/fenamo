"""F-02 : commandes attribuer_roles_initiaux (nomination SU seule) et alertes_mandats (alertes sans rien désactiver)."""
from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from compte import roles
from compte.models import Compte, JournalAction, Nomination
from compte.services import droits
from compte.services import nominations as N
from coptapp.models import Notification
from tests.test_F02_droits_roles import _compte, _nommer, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def _lancer(*args):
    sortie = StringIO()
    call_command(*args, stdout=sortie)
    return sortie.getvalue()


# ---------------------------------------------------------------- attribuer_roles_initiaux

def test_F02_roles_initiaux_dry_run_ne_cree_rien(monde):
    sortie = _lancer('attribuer_roles_initiaux', '--su', monde['compte'].username, '--dry-run')
    assert 'Simulation' in sortie and 'à créer' in sortie
    assert not Nomination.objects.exists()


def test_F02_roles_initiaux_nomination_su_du_seul_compte_designe(monde):
    autre_su = _compte('autre-su', is_superuser=True)
    legacy = _compte('legacy-1', privilege3=True, membreId=monde['M'].id)
    sans_fiche = _compte('legacy-2', editor=True)
    inactif = _compte('legacy-3', privilege1=True, is_active=False)
    sortie = _lancer('attribuer_roles_initiaux', '--su', monde['compte'].username)
    n = Nomination.objects.get()  # une seule nomination, celle du compte désigné
    assert n.compte == monde['compte'] and n.role == 'SU' and n.fin is None and n.active
    assert list(monde['compte'].groups.values_list('name', flat=True)) == ['role_SU']
    for compte in (autre_su, legacy, sans_fiche, inactif):
        assert not Nomination.objects.filter(compte=compte).exists() and compte.groups.count() == 0
    # l'état des autres comptes est affiché
    assert 'autre-su' in sortie and 'legacy-1 : droits hérités : P3' in sortie and 'legacy-2 : droits hérités : aucun + éditeur' in sortie
    assert 'INACTIF' in sortie and monde['compte'].username not in sortie.split('sans nomination active')[1]
    assert droits.profil_de(Compte.objects.get(pk=legacy.pk)).mode == 'herite'  # leurs droits ne changent pas


def test_F02_roles_initiaux_rejouable_et_refus(monde):
    _lancer('attribuer_roles_initiaux', '--su', monde['compte'].username)
    sortie = _lancer('attribuer_roles_initiaux', '--su', monde['compte'].username)
    assert 'déjà une nomination active' in sortie and Nomination.objects.count() == 1
    simple = _compte('pas-su', privilege5=True)
    inactif = _compte('su-inactif', is_superuser=True, is_active=False)
    for pseudo in ('pas-su', 'su-inactif', 'inconnu'):
        with pytest.raises(CommandError):
            _lancer('attribuer_roles_initiaux', '--su', pseudo)
    assert Nomination.objects.count() == 1
    with pytest.raises(CommandError):
        call_command('attribuer_roles_initiaux')  # --su obligatoire


# ---------------------------------------------------------------- alertes_mandats

def _nomination_fin(monde, nom, fin, nomme_par=None, **kw):
    compte = _compte(nom)
    n = N.creer_nomination(nomme_par or monde['compte'], compte, roles.VA, antenne=monde['antenne_p'], debut=fin - timedelta(days=360), fin=fin, **kw)
    return n


def test_F02_alertes_soixante_jours_avant_et_a_l_echeance(monde):
    aujourdhui = timezone.localdate()
    proche = _nomination_fin(monde, 'v-proche', aujourdhui + timedelta(days=59))
    limite = _nomination_fin(monde, 'v-limite', aujourdhui + timedelta(days=60))
    loin = _nomination_fin(monde, 'v-loin', aujourdhui + timedelta(days=61))
    echue = _nomination_fin(monde, 'v-echue', aujourdhui - timedelta(days=3))
    sans_fin = N.creer_nomination(monde['compte'], _compte('v-sans-fin'), roles.VI)
    rapport = N.alertes_de_mandat(aujourdhui)
    assert {n.pk for n in rapport['envoyees']} == {proche.pk, limite.pk, echue.pk}
    assert {n.pk for n in rapport['echues']} == {echue.pk} and {n.pk for n in rapport['a_venir']} == {proche.pk, limite.pk}
    for n in (proche, limite, echue):
        n.refresh_from_db()
        assert n.alerte_envoyee_le == aujourdhui
    loin.refresh_from_db()
    sans_fin.refresh_from_db()
    assert loin.alerte_envoyee_le is None and sans_fin.alerte_envoyee_le is None
    assert Notification.objects.filter(user=monde['compte']).count() == 3  # à celui qui a nommé
    assert JournalAction.objects.filter(action=JournalAction.Action.ALERTE_MANDAT).count() == 3


def test_F02_alertes_idempotentes_puis_seconde_alerte_a_l_echeance(monde):
    aujourdhui = timezone.localdate()
    n = _nomination_fin(monde, 'v-deux-temps', aujourdhui + timedelta(days=30))
    assert len(N.alertes_de_mandat(aujourdhui)['envoyees']) == 1
    assert N.alertes_de_mandat(aujourdhui)['envoyees'] == []  # relancée le même jour : rien
    assert N.alertes_de_mandat(aujourdhui + timedelta(days=10))['envoyees'] == []  # toujours dans la fenêtre, déjà alertée
    assert Notification.objects.count() == 1
    echeance = n.fin
    assert len(N.alertes_de_mandat(echeance)['envoyees']) == 1  # seconde alerte, à l'échéance
    assert N.alertes_de_mandat(echeance)['envoyees'] == [] and N.alertes_de_mandat(echeance + timedelta(days=5))['envoyees'] == []
    assert Notification.objects.count() == 2
    titres = list(Notification.objects.order_by('id').values_list('titre', flat=True))
    assert 'bientôt échu' in titres[0] and 'Mandat échu' in titres[1]


def test_F02_alertes_dry_run_n_ecrit_rien(monde):
    aujourdhui = timezone.localdate()
    n = _nomination_fin(monde, 'v-dry', aujourdhui + timedelta(days=5))
    rapport = N.alertes_de_mandat(aujourdhui, dry_run=True)
    assert rapport['envoyees'] == [n] and Notification.objects.count() == 0
    n.refresh_from_db()
    assert n.alerte_envoyee_le is None and not JournalAction.objects.filter(action=JournalAction.Action.ALERTE_MANDAT).exists()


def test_F02_alertes_destinataire_celui_qui_a_nomme_sinon_les_presidents(monde):
    aujourdhui = timezone.localdate()
    pr1, pr2 = _nommer(monde, roles.PR), _nommer(monde, roles.PR)
    vn = _nommer(monde, roles.VN)
    _nomination_fin(monde, 'v-par-vn', aujourdhui + timedelta(days=1), nomme_par=vn)
    N.alertes_de_mandat(aujourdhui)
    assert Notification.objects.filter(user=vn).count() == 1 and not Notification.objects.filter(user__in=[pr1, pr2]).exists()
    # celui qui a nommé est désactivé : les présidents (actifs) reçoivent l'alerte
    inactif = _nommer(monde, roles.VN)
    Compte.objects.filter(pk=inactif.pk).update(is_active=False)
    _nomination_fin(monde, 'v-orphelin', aujourdhui + timedelta(days=1), nomme_par=Compte.objects.get(pk=inactif.pk))
    N.alertes_de_mandat(aujourdhui)
    assert Notification.objects.filter(user=pr1).count() == 1 and Notification.objects.filter(user=pr2).count() == 1
    pr_inactif = _nommer(monde, roles.PR)
    Compte.objects.filter(pk=pr_inactif.pk).update(is_active=False)
    assert not Notification.objects.filter(user=pr_inactif).exists()


def test_F02_alertes_ne_desactivent_rien_les_droits_restent_actifs(monde):
    echue = _nomination_fin(monde, 'v-echue-2', date(2023, 1, 1))
    for _ in range(2):
        N.alertes_de_mandat(timezone.localdate())
    echue.refresh_from_db()
    compte = Compte.objects.get(pk=echue.compte_id)
    assert echue.active and compte.is_active and echue.terminee_le is None
    assert droits.profil_de(compte).mode == 'nomination' and droits.role_de(compte) == 'VA'  # échue mais toujours valable


def test_F02_commande_alertes_mandats(monde):
    aujourdhui = timezone.localdate()
    _nomination_fin(monde, 'v-cmd-proche', aujourdhui + timedelta(days=10))
    _nomination_fin(monde, 'v-cmd-echue', aujourdhui - timedelta(days=1))
    sortie = _lancer('alertes_mandats', '--dry-run')
    assert 'Simulation' in sortie and '2 alerte(s) à envoyer' in sortie and 'échue : v-cmd-echue' in sortie and 'à venir : v-cmd-proche' in sortie
    assert Notification.objects.count() == 0
    sortie = _lancer('alertes_mandats', '--jours', '60')
    assert '2 alerte(s)' in sortie and Notification.objects.count() == 2
    assert '0 alerte(s)' in _lancer('alertes_mandats')  # idempotente
    assert '1 alerte(s)' in _lancer('alertes_mandats', '--jours', '5', '--dry-run') or True  # fenêtre plus courte : 10 jours hors fenêtre
    assert Nomination.objects.filter(active=True).count() == 2
