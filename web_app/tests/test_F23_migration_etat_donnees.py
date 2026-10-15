"""F-23 / § 4.4 : migration de données 0062 (anciens booléens -> état unique) et commande verifier_etats_membres.
Données fictives uniquement."""
from importlib import import_module
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection, models
from django.db.migrations.executor import MigrationExecutor

from coptapp.models import Membre

AVANT, APRES = '0061_membre_etat_unique', '0062_membre_etat_donnees'

# nom -> (is_delete, is_validate2, is_validate3, renvoye) ; attendu -> (etat, etat_precedent)
CAS = {
    'neuf': ((False, False, False, False), ('saisi', '')),
    'valide_antenne': ((False, True, False, False), ('valide_antenne', '')),
    'actif': ((False, True, True, False), ('actif', '')),
    'ambigu_v3_seul': ((False, False, True, False), ('actif', '')),
    'renvoye_saisi': ((False, False, False, True), ('renvoye', 'saisi')),
    'renvoye_valide': ((False, True, False, True), ('renvoye', 'valide_antenne')),
    'renvoye_actif': ((False, True, True, True), ('renvoye', 'actif')),
    'supprime_saisi': ((True, False, False, False), ('supprime', 'saisi')),
    'supprime_valide': ((True, True, False, False), ('supprime', 'valide_antenne')),
    'supprime_actif': ((True, True, True, False), ('supprime', 'actif')),
    'supprime_v3_seul': ((True, False, True, False), ('supprime', 'actif')),
    'supprime_renvoye': ((True, True, False, True), ('supprime', 'renvoye')),
}


def _migrer(cible):
    executeur = MigrationExecutor(connection)
    executeur.migrate([('coptapp', cible)])
    return MigrationExecutor(connection).loader.project_state([('coptapp', cible)]).apps


def _lire(apps):
    M = apps.get_model('coptapp', 'Membre')
    return {m.nom: ((m.is_delete, m.is_validate2, m.is_validate3, m.renvoye), (m.etat, m.etat_precedent)) for m in M.objects.all()}


@pytest.fixture
def base_0061():
    apps = _migrer(AVANT)
    M = apps.get_model('coptapp', 'Membre')
    for nom, (b, _) in CAS.items():
        M.objects.create(nom=nom, is_delete=b[0], is_validate2=b[1], is_validate3=b[2], renvoye=b[3])
    yield apps
    _migrer(MigrationExecutor(connection).loader.graph.leaf_nodes('coptapp')[0][1])


@pytest.mark.django_db(transaction=True)
def test_migration_0062_correspondance_aller_retour_et_idempotence(base_0061):
    apres = _migrer(APRES)
    lu = _lire(apres)
    for nom, (b, attendu) in CAS.items():
        assert lu[nom][1] == attendu, nom
        assert lu[nom][0] == b, f'{nom} : le sens direct ne modifie pas les booléens'

    # rejouable sans dégâts, y compris sur un état posé après coup (valide_province : is_validate2 seul)
    M = apres.get_model('coptapp', 'Membre')
    M.objects.filter(nom='neuf').update(etat='valide_province', is_validate2=True)
    migration = import_module(f'coptapp.migrations.{APRES}')
    migration.vers_etat_unique(apres, None)
    migration.vers_etat_unique(apres, None)
    relu = _lire(apres)
    assert relu['neuf'][1] == ('valide_province', '')
    assert {n: v[1] for n, v in relu.items() if n != 'neuf'} == {n: a for n, (_, a) in CAS.items() if n != 'neuf'}

    # sens inverse : booléens recalculés depuis l'état
    M.objects.filter(nom='neuf').update(etat='saisi', is_validate2=False)
    avant = _migrer(AVANT)
    inverse = _lire(avant)
    for nom, (b, _) in CAS.items():
        attendu = b
        if nom == 'ambigu_v3_seul':
            attendu = (False, True, True, False)  # l'ambiguïté est tranchée par l'état : actif => is_validate2
        if nom == 'supprime_v3_seul':
            attendu = (True, True, True, False)
        if nom in ('renvoye_valide', 'renvoye_actif'):
            attendu = (False, False, False, True)  # règle des miroirs du modèle : un renvoyé n'a aucune validation
        if nom == 'supprime_renvoye':
            attendu = (True, False, False, False)  # supprimé : validations de l'état d'avant (renvoyé : aucune), renvoye faux
        assert inverse[nom][0] == attendu, nom
    # remontée après un retour arrière
    assert {n: v[1] for n, v in _lire(_migrer(APRES)).items()}['actif'] == ('actif', '')


@pytest.mark.django_db(transaction=True)
def test_migration_0062_par_lots(base_0061, monkeypatch):
    migration = import_module(f'coptapp.migrations.{APRES}')
    monkeypatch.setattr(migration, 'LOT', 2)
    migration.vers_etat_unique(base_0061, None)
    assert {n: v[1] for n, v in _lire(base_0061).items()} == {n: a for n, (_, a) in CAS.items()}


@pytest.mark.django_db
def test_commande_verifier_etats_membres():
    ok = Membre.objects.create(nom='Cohérent', idf='IDF-OK')
    Membre.objects.filter(pk=ok.pk).update(etat='actif')  # miroirs recalculés par update()
    base = models.QuerySet(model=Membre)
    ecart = Membre.objects.create(nom='Écart', idf='IDF-ECART')
    base.filter(pk=ecart.pk).update(etat='actif')  # miroirs laissés à False
    ambigu = Membre.objects.create(nom='Ambigu', idf='IDF-AMB')
    base.filter(pk=ambigu.pk).update(etat='actif', is_validate3=True, is_validate2=False)
    nom_prive = 'Écart'

    sortie = StringIO()
    call_command('verifier_etats_membres', stdout=sortie)
    texte = sortie.getvalue()
    assert 'Membres lus : 3' in texte and 'actif : 3' in texte
    assert f'id={ecart.pk} idf=IDF-ECART' in texte and 'Écarts état/miroirs : 2' in texte
    assert 'Cas ambigus' in texte and 'validation province sans validation antenne' in texte
    assert nom_prive not in texte.replace('Écarts', '')  # aucun nom de membre
    assert Membre.objects.get(pk=ecart.pk).is_validate2 is False  # sans --corriger : rien n'est écrit

    call_command('verifier_etats_membres', '--corriger', '--dry-run', stdout=StringIO())
    assert Membre.objects.get(pk=ecart.pk).is_validate2 is False

    sortie = StringIO()
    call_command('verifier_etats_membres', '--corriger', stdout=sortie)
    assert '2 membre(s) resynchronisé(s)' in sortie.getvalue()
    for pk in (ecart.pk, ambigu.pk):
        m = Membre.objects.get(pk=pk)
        assert m.etat == 'actif' and m.is_validate2 and m.is_validate3  # seul le miroir bouge, jamais l'état
    sortie = StringIO()
    call_command('verifier_etats_membres', stdout=sortie)
    assert 'Écarts état/miroirs : 0' in sortie.getvalue()


def test_F23_migration_0062_miroirs_identiques_a_ceux_du_modele():
    """La copie de la règle dans la migration doit rester identique à miroirs_de() pour toutes les combinaisons."""
    from coptapp.models import ETATS_MEMBRE, miroirs_de
    migration = import_module(f'coptapp.migrations.{APRES}')
    for etat in ETATS_MEMBRE:
        for precedent in ('',) + ETATS_MEMBRE:
            assert migration.miroirs(etat, precedent) == miroirs_de(etat, precedent), (etat, precedent)
