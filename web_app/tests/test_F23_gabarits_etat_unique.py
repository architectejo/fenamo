"""F-23 : « Valider tout le monde », bandeau du renvoi, destination du renvoi, états valide_province et renvoye dans les gabarits."""
from datetime import date

from django.urls import reverse

from compte import roles
from compte.models import Compte, Nomination
from coptapp.models import Membre
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def _membre(jeu, nom, etat):
    m = Membre.objects.create(nom=nom, date_naissance=date(1990, 1, 1), province=jeu['province'], antenne=jeu['antenne'],
                              structure=jeu['association'])
    Membre.objects.filter(pk=m.pk).update(etat=etat)
    m.refresh_from_db()
    return m


def _valideur(jeu, role):
    compte = Compte.objects.create_user(f'val-{role.lower()}', password='x')
    kw = {'antenne': jeu['antenne']} if role in (roles.VA, roles.AT) else {'coordination': jeu['province']} if role == roles.VP else {}
    Nomination.objects.create(compte=compte, role=role, nomme_par=jeu['compte'], **kw)
    return compte


def test_F23_liste_bouton_valider_tout_le_monde_et_modale(client, jeu):
    _membre(jeu, 'A Valider', 'saisi')
    client.force_login(jeu['compte'])
    html = client.get(reverse('liste-membre')).content.decode()
    assert 'Valider tout le monde' in html and 'id="modale-valider-tous"' in html and reverse('valider-tous') in html
    assert 'hx-post=' in html and 'name="etat"' in html and 'membresMaj' in html
    # filtre sans résultat validable : aucun bouton
    vide = client.get(reverse('liste-membre'), {'q': 'introuvable-zzz'}, HTTP_HX_REQUEST='true').content.decode()
    assert 'Valider tout le monde' not in vide


def test_F23_valider_tous_par_htmx_204_et_evenement(client, jeu):
    m = _membre(jeu, 'A Valider', 'saisi')
    client.force_login(jeu['compte'])
    r = client.post(reverse('valider-tous'), {'etat': 'saisi'}, HTTP_HX_REQUEST='true')
    assert r.status_code == 204 and 'membresMaj' in r['HX-Trigger'] and 'modaleFermer' in r['HX-Trigger']
    m.refresh_from_db()
    assert m.etat != 'saisi'


def test_F23_pas_de_bouton_valider_tous_sans_droit(client, jeu):
    _membre(jeu, 'Visible', 'saisi')
    lecteur = Compte.objects.create_user('lecteur', password='x', privilege4=True)
    client.force_login(lecteur)
    r = client.get(reverse('liste-membre'))
    assert 'Valider tout le monde' not in r.content.decode()


def test_F23_bandeau_et_destination_du_renvoi(client, jeu):
    for etat, destination in (('valide_province', 'à la coordination provinciale'), ('valide_antenne', "à l'antenne"), ('saisi', "à l'agent")):
        m = _membre(jeu, f'Dossier {etat}', etat)
        client.force_login(jeu['compte'])
        html = client.get(reverse('membre-view', kwargs={'id': m.id})).content.decode().replace('&#x27;', "'")
        assert reverse('renvoyer-membre', kwargs={'id': m.id}) in html, etat
        assert f'Renvoyer le dossier {destination}' in html, etat
    recule = _membre(jeu, 'Recule', 'saisi')
    Membre.objects.filter(pk=recule.pk).update(motif_renvoi='Photo floue')
    html = client.get(reverse('membre-view', kwargs={'id': recule.id})).content.decode().replace('&#x27;', "'")
    assert "Dossier reculé d'un cran" in html and 'Photo floue' in html
    renvoye = _membre(jeu, 'Renvoye', 'renvoye')
    Membre.objects.filter(pk=renvoye.pk).update(motif_renvoi='Doublon')
    html = client.get(reverse('membre-view', kwargs={'id': renvoye.id})).content.decode()
    assert 'Dossier renvoyé' in html and 'Doublon' in html


def test_F23_liste_filtres_et_badges_valide_province_et_renvoye(client, jeu):
    _membre(jeu, 'Province Un', 'valide_province')
    _membre(jeu, 'Renvoye Un', 'renvoye')
    client.force_login(jeu['compte'])
    html = client.get(reverse('liste-membre')).content.decode()
    for code, libelle in (('valide_province', 'Validé province'), ('renvoye', 'Renvoyé')):
        assert f'value="{code}"' in html and f'etat--{code}' in html and libelle in html
    filtre = client.get(reverse('liste-membre'), {'etat': 'renvoye'}, HTTP_HX_REQUEST='true').content.decode()
    assert 'Renvoye Un' in filtre and 'Province Un' not in filtre


def test_F23_tableau_de_bord_cartes_et_graphique_a_cinq_valeurs(client, jeu):
    _membre(jeu, 'Province Deux', 'valide_province')
    _membre(jeu, 'Renvoye Deux', 'renvoye')
    client.force_login(jeu['compte'])
    html = client.get(reverse('tableau-bord')).content.decode()
    assert 'validé province' in html and 'Dossiers renvoyés' in html
    for etat in ('saisi', 'valide_antenne', 'valide_province', 'actif', 'renvoye'):
        assert f'barre--{etat}' in html, etat
