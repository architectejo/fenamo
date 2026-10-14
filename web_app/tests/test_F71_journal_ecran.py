"""F-71 : journal d'activités en lecture seule, réservé au super-utilisateur (liste paginée, filtres, fragment HTMX)."""
from django.urls import reverse

from compte.models import Compte, JournalAction
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_F71_journal_reserve_au_su(client, jeu):
    assert client.get(reverse('journal')).status_code == 302
    simple = Compte.objects.create_user('simple', password='x', privilege5=True)
    client.force_login(simple)
    assert client.get(reverse('journal')).status_code == 403
    assert client.post(reverse('journal')).status_code in (403, 405)


def test_F71_journal_liste_filtres_et_fragment(client, jeu):
    client.force_login(jeu['compte'])
    JournalAction.objects.create(auteur=jeu['compte'], action='validation', objet_libelle='Membre Fictif', motif='ok',
                                 avant={'secret': 'x'}, apres={'secret': 'y'})
    page = client.get(reverse('journal')).content.decode()
    assert 'Journal d' in page and 'Validation' in page and 'Membre Fictif' in page
    assert "'secret'" not in page and '&quot;secret' not in page  # jamais avant/après
    frag = client.get(reverse('journal'), {'action': 'validation', 'q': 'Fictif'}, HTTP_HX_REQUEST='true').content.decode()
    assert '<html' not in frag and 'Membre Fictif' in frag
    vide = client.get(reverse('journal'), {'q': 'introuvable-zzz'}, HTTP_HX_REQUEST='true').content.decode()
    assert 'Aucune entrée' in vide
    assert client.get(reverse('journal'), {'du': 'pas-une-date', 'page': 'abc'}).status_code == 200


def test_F28_ecrans_migres_repondent_sur_la_coque(client, jeu):
    client.force_login(jeu['compte'])
    for nom, kw in (('str-list', {}), ('edit-structure', {'id': jeu['association'].id}), ('view-moto', {'id': jeu['moto'].id}),
                    ('notifys', {}), ('list-message', {})):
        r = client.get(reverse(nom, kwargs=kw))
        assert r.status_code == 200, nom
        html = r.content.decode()
        assert 'class="coque"' in html and 'bootstrap' not in html.lower(), nom
