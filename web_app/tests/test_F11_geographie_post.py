"""F-10 / F-11 : coordination et antenne sans nom = erreur 400 propre (jamais 500)."""
from django.test import Client
from django.urls import reverse

from tests.test_F21_matrice_routes import acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_F11_ville_sans_nom_400_puis_ajout(acteurs):
    c = Client(raise_request_exception=False)
    c.force_login(acteurs['comptes']['su'])
    url = reverse('add-ville', kwargs={'id': acteurs['province'].id})
    assert c.post(url, {}).status_code == 400
    assert c.post(url, {'nom': '  '}).status_code == 400
    assert c.post(url, {'nom': 'Nouvelle'}).status_code == 200


def test_F10_province_sans_nom_400(acteurs):
    c = Client(raise_request_exception=False)
    c.force_login(acteurs['comptes']['su'])
    assert c.post(reverse('add-province'), {}).status_code == 400
    assert c.post(reverse('add-province'), {'nom': 'Nouvelle', 'sigle': 'NV'}).status_code == 200


def test_F11_notification_et_message_d_ajout_d_antenne_sans_requete_en_trop(acteurs):
    from coptapp.models import Notification, Ville
    c = Client()
    c.force_login(acteurs['comptes']['su'])
    r = c.post(reverse('add-ville', kwargs={'id': acteurs['province'].id}), {'nom': 'Kimbanseke'})
    assert 'coordination provinciale' in r.content.decode()
    notif = Notification.objects.get(titre="Ajout d'une antenne")
    assert 'Kimbanseke' in notif.description and Ville.objects.filter(nom='Kimbanseke').count() == 1


def test_F11_association_sans_ville_choix_de_l_antenne_sans_500(acteurs):
    from coptapp.models import AssociationMembre
    c = Client(raise_request_exception=False)
    c.force_login(acteurs['comptes']['su'])
    sans_ville = AssociationMembre.objects.create(nom='Sans ville', province=acteurs['province'], num_justice='F-9')
    url = reverse('ville-select', kwargs={'id': sans_ville.id})
    assert c.get(url).status_code == 200
    assert c.post(url, {'ville': '  '}).status_code == 400
    assert c.post(url, {'ville': 'lemba'}).status_code == 302
    sans_ville.refresh_from_db()
    assert sans_ville.ville.nom == 'LEMBA'


def test_F11_session_d_une_association_dont_le_compte_n_a_pas_de_ville(acteurs):
    from coptapp.models import Membre
    Membre.objects.filter(pk=acteurs['membre'].pk).update(ville=None)
    c = Client(raise_request_exception=False)
    c.force_login(acteurs['comptes']['su'])
    assert c.get(reverse('structure-admin', kwargs={'id': acteurs['association'].id})).status_code == 200
