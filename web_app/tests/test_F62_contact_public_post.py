"""F-62 : formulaire de contact public de l'ancien site : champ manquant ou date libre invalide = 400 propre."""
from django.test import Client
from django.urls import reverse

from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_F62_contact_public_sans_champ_ou_date_invalide_400(db):
    c = Client(raise_request_exception=False)
    url = reverse('home')
    assert c.post(url, {}).status_code == 400
    assert c.post(url, {'nom': 'A', 'mail': 'a@example.invalid', 'date': 'pas-une-date'}).status_code == 400
    c.post(url, {'nom': 'A', 'mail': 'a@example.invalid', 'date': '2026-10-13'})
    # (la page de l'ancien site, à supprimer, peut échouer sans image de fond configurée : seul l'enregistrement compte)
    from virtrine.models import Contact
    assert Contact.objects.filter(nom='A', date='2026-10-13').exists()
