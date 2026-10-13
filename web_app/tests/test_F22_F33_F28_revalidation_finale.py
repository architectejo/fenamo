"""Revalidation finale indépendante : controler_pdf (F-22), attribuer_engin (F-33/F-35), filtre d'état de la liste (F-28)."""
import time
from datetime import date

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from compte.models import JournalAction
from coptapp import validators
from coptapp.models import Membre, Moto
from coptapp.services.engins import attribuer_engin
from tests.test_F21_matrice_routes import acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def pdf(corps=b''):
    return SimpleUploadedFile('p.pdf', b'%PDF-1.4\n1 0 obj<< ' + corps + b' >>endobj\n%%EOF\n', 'application/pdf')


def test_F22_trois_mo_de_codes_hexa_refuses_ou_acceptes_en_moins_de_0_3_s():
    f = SimpleUploadedFile('p.pdf', b'%PDF-1.4\n/' + b'#41' * (1024 * 1024) + b'\n%%EOF\n', 'application/pdf')
    debut = time.perf_counter()
    try:
        validators.controler_pdf(f)
    except ValidationError:
        pass
    assert time.perf_counter() - debut < 0.3


def test_F22_police_avec_prefixe_aaaaaa_acceptee():
    validators.controler_pdf(pdf(b'/BaseFont /AAAAAA+Arial /Names /JSON /AAPL'))


@pytest.mark.parametrize('nom', [b'/JavaScript', b'/Java#53cript', b'/JS', b'/AA', b'/OpenAction', b'/Launch',
                                 b'/EmbeddedFile', b'/J#53', b'/#4aS', b'/JS(x)', b'/AA<<'])
def test_F22_elements_actifs_refuses(nom):
    with pytest.raises(ValidationError):
        validators.controler_pdf(pdf(nom + b' '))


def test_F22_pdf_sans_eof_refuse():
    with pytest.raises(ValidationError):
        validators.controler_pdf(SimpleUploadedFile('p.pdf', b'%PDF-1.4\n1 0 obj<< >>endobj', 'application/pdf'))


def test_F22_controle_execute_une_seule_fois_par_envoi(monkeypatch):
    compte = {'n': 0}
    reel = validators._INTERDIT_EXACT

    class Espion:
        def search(self, contenu):
            compte['n'] += 1
            return reel.search(contenu)
    monkeypatch.setattr(validators, '_INTERDIT_EXACT', Espion())
    f = pdf()
    validators.valider_piece(f)      # type_reel_piece -> controler_pdf
    validators.controler_pdf(f)
    validators.type_reel_piece(f)
    assert compte['n'] == 1


# ---------------------------------------------------------------- attribuer_engin

def _moto(acteurs, numero='ATT-1'):
    return Moto.objects.create(proprietaire=acteurs['membre'], abonnement=date(2030, 1, 1), numero=numero)


def test_F33_attribuer_engin_ecrit_par_colonnes_et_journalise(acteurs, monkeypatch):
    moto = _moto(acteurs)
    vus = []
    reel = Moto.save
    monkeypatch.setattr(Moto, 'save', lambda self, *a, **k: (vus.append(k.get('update_fields')), reel(self, *a, **k))[1])
    assert attribuer_engin(acteurs['comptes']['su'], acteurs['membre'], 'ATT-1') == 'attribue'
    assert vus and all(u and set(u) <= {'motard_id', 'mise_a_jour'} for u in vus)
    moto.refresh_from_db()
    assert moto.motard_id == str(acteurs['membre'].id)
    assert JournalAction.objects.filter(action=JournalAction.Action.RATTACHEMENT, objet_id=moto.id).count() == 1


@pytest.mark.parametrize('profil', ['nu', 'p4', 'ed'])
def test_F33_attribuer_engin_refuse_sans_droit_sur_le_membre_cible(acteurs, profil):
    moto = _moto(acteurs)
    with pytest.raises(PermissionDenied):
        attribuer_engin(acteurs['comptes'][profil], acteurs['membre'], 'ATT-1')
    moto.refresh_from_db()
    assert moto.motard_id in (None, '') and not JournalAction.objects.filter(action=JournalAction.Action.RATTACHEMENT).exists()


def test_F33_attribuer_engin_refuse_pour_un_membre_cible_supprime(acteurs):
    moto = _moto(acteurs)
    Membre.objects.filter(pk=acteurs['membre'].pk).update(is_delete=True)
    acteurs['membre'].refresh_from_db()
    with pytest.raises(PermissionDenied):
        attribuer_engin(acteurs['comptes']['su'], acteurs['membre'], 'ATT-1')
    moto.refresh_from_db()
    assert moto.motard_id in (None, '')


def test_F33_attribuer_engin_exige_aussi_le_droit_sur_l_engin(acteurs):
    """p1 perd le droit de modifier l'engin quand le propriétaire est validé au-delà de son niveau (F-33)."""
    moto = _moto(acteurs)
    Membre.objects.filter(pk=acteurs['membre'].pk).update(is_validate3=True)
    acteurs['membre'].refresh_from_db()
    with pytest.raises(PermissionDenied):
        attribuer_engin(acteurs['comptes']['p1'], acteurs['membre'], 'ATT-1')
    moto.refresh_from_db()
    assert moto.motard_id in (None, '')


# ---------------------------------------------------------------- F-28 filtre d'état

def test_F28_filtre_etat_a_tiret_ignore_et_snake_case_filtre(client, acteurs):
    client.force_login(acteurs['comptes']['su'])
    url = reverse('liste-membre')
    sans = client.get(url).content.decode()
    tiret = client.get(url, {'etat': 'valide-antenne'}).content.decode()
    assert 'Membre' in sans and acteurs['membre'].nom in sans
    assert acteurs['membre'].nom in tiret  # valeur inconnue : ne filtre pas
    assert 'value="valide-antenne"' not in tiret and 'etat=valide-' not in tiret
    ok = client.get(url, {'etat': 'valide_antenne'}).content.decode()
    assert acteurs['membre'].nom in ok  # le membre du jeu est validé niveau 2
    assert acteurs['membre'].nom not in client.get(url, {'etat': 'actif'}).content.decode()
