"""F-40, F-62 : corrections de revue (cible obligatoire à la publication, aperçu réservé, notification des messages du site, contactView)."""
import pytest
from django.urls import reverse

from compte import roles
from coptapp.models import Communique, Notification
from tests.test_F40_communiques import equipe  # noqa: F401
from tests.test_F02_droits_roles import _compte, _nommer, acteurs_roles, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401
from virtrine.models import Contact
from virtrine.services import contact as contact_service


def test_F40_post_sans_cible_422_jamais_national(client, monde, equipe):
    client.force_login(equipe['ED'])
    avant = Communique.objects.count()
    for donnees in ({'titre': 'T', 'message': 'M'}, {'titre': 'T', 'message': 'M', 'cible': '  '}):
        r = client.post(reverse('message'), donnees, HTTP_HX_REQUEST='true')
        assert r.status_code == 422 and list(r.context['erreurs']) == ['cible']
    assert Communique.objects.count() == avant


def test_F40_apercu_get_refuse_sans_droit_de_publier(client, monde, equipe):
    for cle in ('PR', 'VN', 'VA_P', 'VI_NAT'):
        client.force_login(equipe[cle])
        assert client.get(reverse('message'), {'cible': 'national'}).status_code == 403, cle
    client.force_login(equipe['ED'])
    r = client.get(reverse('message'), {'cible': 'national'})
    assert r.status_code == 200 and r.context['nb_destinataires'] >= 0


def test_F40_modale_sans_cible_sert_deja_le_resume_national(client, monde, equipe):
    client.force_login(equipe['ED'])
    r = client.get(reverse('message'), HTTP_HX_REQUEST='true')
    assert r.context['nb_destinataires'] > 0 and 'hx-trigger="change from' in r.content.decode()


def test_F62_notification_message_du_site_pour_ed_et_su_seulement(monde, equipe):
    from compte.services.perimetre import notifications_du_perimetre
    contact = contact_service.enregistrer(
        {'nom': 'Jean', 'mail': 'j@example.org', 'telephone': '', 'objet': 'Objet', 'message': 'Bonjour à tous'})
    notif = Notification.objects.get(titre=contact_service.TITRE_NOTIFICATION)
    assert contact.pk
    voit = lambda u: notif in notifications_du_perimetre(u)  # noqa: E731
    assert voit(monde['compte']) and voit(equipe['ED'])
    for cle in ('PR', 'VN', 'VP_P', 'VA_P', 'AT_P', 'VI_NAT'):
        assert not voit(equipe[cle]), cle


def test_F62_contact_view_methodes(client, monde, equipe):
    c = Contact.objects.create(nom='A', mail='a@x.org', raison='R', description='x' * 12, traiter=False)
    client.force_login(equipe['ED'])
    url = reverse('contact-view', args=[c.pk])
    assert client.put(url).status_code == 405 and client.delete(url).status_code == 405
    assert client.get(url).status_code == 200
