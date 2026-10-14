"""F-23 / F-30 : bouton « Renvoyer » de la fiche (modale avec motif), motif affiché, liste des engins sur la coque."""
from datetime import date

from django.urls import reverse

from compte import roles
from compte.models import Compte, Nomination
from coptapp.models import Membre
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def _valideur(jeu):
    compte = Compte.objects.create_user('valideur-national', password='x')
    Nomination.objects.create(compte=compte, role=roles.VN, nomme_par=jeu['compte'])
    return compte


def _saisi(jeu, **kw):
    return Membre.objects.create(nom='A Renvoyer', date_naissance=date(1990, 1, 1), province=jeu['province'], antenne=jeu['antenne'],
                                 structure=jeu['association'], is_validate2=True, **kw)


def test_F23_fiche_propose_renvoyer_avec_motif_obligatoire(client, jeu):
    membre = _saisi(jeu)
    client.force_login(jeu['compte'])
    html = client.get(reverse('membre-view', kwargs={'id': membre.id})).content.decode()
    assert reverse('renvoyer-membre', kwargs={'id': membre.id}) in html
    assert 'name="motif"' in html and 'Motif du renvoi' in html and 'data-motif-requis' in html


def test_F23_renvoi_puis_motif_affiche_sur_la_fiche(client, jeu):
    membre = _saisi(jeu)
    client.force_login(jeu['compte'])
    r = client.post(reverse('renvoyer-membre', kwargs={'id': membre.id}), {'motif': 'Photo illisible'}, follow=True)
    assert r.status_code == 200
    fiche = client.get(reverse('membre-view', kwargs={'id': membre.id})).content.decode()
    assert 'Dossier renvoyé' in fiche and 'Photo illisible' in fiche


def test_F23_pas_de_bouton_renvoyer_sans_droit(client, jeu):
    membre = _saisi(jeu)
    lecteur = Compte.objects.create_user('lecture-seule', password='x', privilege4=True)
    client.force_login(lecteur)
    r = client.get(reverse('membre-view', kwargs={'id': membre.id}))
    if r.status_code == 200:
        assert reverse('renvoyer-membre', kwargs={'id': membre.id}) not in r.content.decode()


def test_F30_liste_des_engins_page_et_fragment(client, jeu):
    client.force_login(jeu['compte'])
    page = client.get(reverse('engin-liste')).content.decode()
    assert 'class="coque"' in page and 'Engins' in page and jeu['moto'].numero in page and reverse('engin-liste') in page
    frag = client.get(reverse('engin-liste'), {'q': jeu['moto'].numero}, HTTP_HX_REQUEST='true').content.decode()
    assert '<html' not in frag and jeu['moto'].numero in frag
    vide = client.get(reverse('engin-liste'), {'q': 'zzzz'}, HTTP_HX_REQUEST='true').content.decode()
    assert 'Aucun engin ne correspond' in vide
