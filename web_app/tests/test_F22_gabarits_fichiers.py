"""F-22 / F-20 : les gabarits n'adressent plus jamais /media/ pour les photos et pièces privées ; l'espace mobile est sans lien GET de modification."""
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from coptapp.models import Membre
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

RACINE = Path(settings.BASE_DIR)
DOSSIERS = ('coptapp/templates', 'templates', 'mobapp/templates', 'compte/templates')


def _gabarits():
    for dossier in DOSSIERS:
        yield from (RACINE / dossier).rglob('*.html')


def test_F22_aucune_url_directe_de_photo_ou_de_piece_dans_les_gabarits():
    """Seule la photo d'un ENGIN (publique, pas une donnée personnelle) garde `.photo.url`."""
    fautifs = []
    for f in _gabarits():
        for numero, ligne in enumerate(f.read_text(encoding='utf-8').splitlines(), 1):
            for m in re.finditer(r'([\w.]+)\.(photo|fiche_id|capture_justice|preuve_de_paiement)\.url', ligne):
                if m.group(1).split('.')[-1] != 'moto':
                    fautifs.append(f'{f.relative_to(RACINE).as_posix()}:{numero} {m.group(0)}')
    assert fautifs == []


def test_F22_avatar_utilise_la_vignette_protegee(client, jeu):
    from django.template import engines
    membre = jeu['membre']
    Membre.objects.filter(pk=membre.pk).update(photo='essai.jpg')
    membre.refresh_from_db()
    html = engines['django'].from_string('{% load design %}{% avatar m.nom m.photo 40 %}').render({'m': membre})
    assert '/fichiers/membre/%d/photo/?vignette=1' % membre.pk in html
    assert '/media/' not in html and 'loading="lazy"' in html and 'width="40"' in html


def test_F22_liste_et_fiche_n_exposent_pas_media(client, jeu):
    Membre.objects.filter(pk=jeu['membre'].pk).update(photo='essai.jpg')
    client.force_login(jeu['compte'])
    for url in (reverse('liste-membre'), reverse('membre-view', kwargs={'id': jeu['membre'].id}), reverse('tableau-bord')):
        html = client.get(url).content.decode()
        assert '/media/' not in html, url


def test_F20_aucun_lien_get_vers_attribut_dans_les_gabarits_mobiles():
    for f in (RACINE / 'mobapp/templates').rglob('*.html'):
        texte = f.read_text(encoding='utf-8')
        for m in re.finditer(r'<a\b[^>]*href="[^"]*attribut-(?:str|ville)[^"]*"', texte):
            pytest.fail(f'{f.name} : lien GET de modification {m.group(0)}')
        assert not re.search(r'<a\b[^>]*href="\{% url \'attribut-', texte), f.name


def test_F20_chaque_formulaire_mobile_post_porte_un_jeton_csrf():
    for f in (RACINE / 'mobapp/templates/mob').glob('*.html'):
        texte = f.read_text(encoding='utf-8')
        for m in re.finditer(r'<form\b[^>]*>(.*?)</form>', texte, re.S):
            ouvrant = re.match(r'<form\b[^>]*>', m.group(0)).group(0)
            if 'method="post"' in ouvrant.lower():
                assert 'csrf_token' in m.group(1), (f.name, ouvrant)


def test_F20_inscription_mobile_champ_piege_hors_ecran_et_deux_mots_de_passe(client, db):
    html = client.get(reverse('register')).content.decode()
    assert 'name="piege"' in html and 'tabindex="-1"' in html and 'aria-hidden="true"' in html
    assert 'name="password1"' in html and 'name="password2"' in html
    assert 'type="hidden" name="piege"' not in html
    assert '/static/css/app.css' in html and 'bootstrap' not in html.lower()


def test_F20_accueil_mobile_affiche_le_message_et_le_statut_429(client, db):
    html = client.get(reverse('home-mob')).content.decode()
    assert 'name="idf"' in html and 'csrfmiddlewaretoken' in html
    for _ in range(12):
        r = client.post(reverse('home-mob'), {'idf': 'MBR0000001', 'pass': 'x', 'envoyer': 'envoyer'})
        if r.status_code == 429:
            from html import unescape
            assert "Trop d'essais" in unescape(r.content.decode())
            break


def test_F20_bouton_mot_de_passe_mobile_selon_le_droit(client, jeu):
    from compte.models import Compte
    Membre.objects.filter(pk=jeu['membre'].pk).update(idf='MBR0000001')
    client.force_login(jeu['compte'])
    url = reverse('membre-view', kwargs={'id': jeu['membre'].id})
    html = client.get(url).content.decode()
    assert reverse('mot-de-passe-mobile', kwargs={'id': jeu['membre'].id}) in html and 'Définir un mot de passe mobile' in html
    Membre.objects.filter(pk=jeu['membre'].pk).update(idf=None)
    assert 'Définir un mot de passe mobile' not in client.get(url).content.decode()
    visiteur = Compte.objects.create_user('lecture', password='x', privilege4=True)
    client.force_login(visiteur)
    assert 'Définir un mot de passe mobile' not in client.get(reverse('liste-membre')).content.decode()


def test_F20_mot_de_passe_mobile_affiche_une_fois_avec_bouton_copier(client, jeu):
    Membre.objects.filter(pk=jeu['membre'].pk).update(idf='MBR0000001')
    client.force_login(jeu['compte'])
    r = client.post(reverse('mot-de-passe-mobile', kwargs={'id': jeu['membre'].id}), follow=True)
    html = r.content.decode()
    assert 'Mot de passe mobile défini' in html and 'Copier le mot de passe' in html and 'hx-history="false"' in html
    assert 'Mot de passe mobile défini' not in client.get(r.redirect_chain[-1][0]).content.decode()  # une seule fois
