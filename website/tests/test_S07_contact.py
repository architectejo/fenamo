"""S-07 : formulaire de contact. L'API est simulée avec les fixtures `api_site_contact_*.json` ; aucun appel réel."""
import re
import time

import pytest
from django.test import Client

from tests.conftest import charger

URL = "/contact/"
VALIDE = {
    "nom": "Jean Mukendi",
    "telephone": "+243 812 345 678",
    "mail": "",
    "objet": "Question générale",
    "message": "Bonjour, comment renouveler la carte d'un membre de mon association ?",
}


def jeton(reponse):
    m = re.search(r'name="ouverture" value="([^"]+)"', reponse.content.decode())
    assert m, "jeton d'ouverture absent"
    return m.group(1)


def envoyer(client, donnees=None, jeton_=None, **entetes):
    """Ouvre le formulaire puis l'envoie (jeton d'ouverture signé relu dans la page)."""
    ouverture = jeton_ if jeton_ is not None else jeton(client.get(URL))
    return client.post(URL, {**VALIDE, **(donnees or {}), "ouverture": ouverture}, **entetes)


def jeton_valide():
    from services import contact

    return contact.jeton_ouverture()


def posts(api):
    return [a for a in api.appels if a[0] == "POST"]


def test_S07_le_formulaire_s_affiche_avec_champ_piege_accessible(client, api):
    rep = client.get(URL)
    html = rep.content.decode()
    assert rep.status_code == 200
    for nom in ("nom", "telephone", "mail", "objet", "message", "ouverture", "csrfmiddlewaretoken", "site_web"):
        assert f'name="{nom}"' in html
    piege = re.search(r'<div class="champ-piege"[^>]*>.*?</div>', html, re.S).group(0)
    assert 'aria-hidden="true"' in piege and 'tabindex="-1"' in piege and 'autocomplete="off"' in piege
    assert '<label class="champ-libelle" for="c-nom">' in html and 'aria-live="polite"' in html
    assert "no-store" in rep["Cache-Control"]
    assert not posts(api)


def test_S07_envoi_nominal_vers_l_api_avec_la_cle(client, api, settings):
    settings.SITE_API_KEY = "fsk_abcd1234_secret"
    avant = int(time.time())
    rep = envoyer(client)
    assert rep.status_code == 200
    html = rep.content.decode()
    assert "Message envoyé" in html and "<form" not in html
    assert "Jean Mukendi" not in html  # aucun écho des données
    assert len(api.envois) == 1
    envoi = api.envois[0]
    assert envoi["headers"]["X-Site-Key"] == "fsk_abcd1234_secret"
    data = envoi["data"]
    assert data["nom"] == "Jean Mukendi" and data["telephone"] == "+243 812 345 678" and data["objet"] == "Question générale"
    assert data["site_web"] == ""
    assert avant - 2 <= data["ouvert_le"] <= int(time.time())


def test_S07_ouvert_le_vient_du_jeton_signe_jamais_du_visiteur(client, api):
    ouverture = jeton(client.get(URL))
    rep = client.post(URL, {**VALIDE, "ouverture": ouverture, "ouvert_le": "1"})
    assert rep.status_code == 200
    assert api.envois[0]["data"]["ouvert_le"] > 1_000_000


def test_S07_jeton_falsifie_ou_absent_rien_n_est_envoye_et_la_saisie_reste(client, api):
    rep = envoyer(client, jeton_="1700000000:abc:falsifie")
    assert rep.status_code == 400
    html = rep.content.decode()
    assert "resté ouvert trop longtemps" in html and "Jean Mukendi" in html
    assert not posts(api)
    rep = client.post(URL, VALIDE)
    assert rep.status_code == 400 and not posts(api)


def test_S07_champ_piege_rempli_reponse_de_succes_sans_appel_api(client, api):
    rep = envoyer(client, {"site_web": "http://spam.example"})
    assert rep.status_code == 200 and "Message envoyé" in rep.content.decode()
    assert not posts(api)


def test_S07_400_erreurs_a_cote_des_champs_et_saisie_conservee(client, api):
    api.repondre_fixture("contact/", "api_site_contact_invalide.json")
    rep = envoyer(client, {"nom": "J", "message": "court <b>x</b>"})
    assert rep.status_code == 400
    html = rep.content.decode()
    assert 'id="c-nom-err"' in html and "Indiquez votre nom." in html
    assert 'id="c-msg-err"' in html and "Le message est trop court" in html
    assert "Indiquez un numéro de téléphone ou une adresse e-mail" in html  # hors champ : résumé en haut
    assert 'aria-invalid="true"' in html and 'aria-describedby="c-nom-err"' in html
    assert "court &lt;b&gt;x&lt;/b&gt;" in html and "<b>x</b>" not in html  # échappé, aucun HTML conservé
    assert "Le message n&#x27;est pas encore envoyé" in html or "pas encore envoyé" in html


def test_S07_htmx_renvoie_le_fragment_en_200_meme_en_erreur(client, api):
    api.repondre_fixture("contact/", "api_site_contact_invalide.json")
    rep = envoyer(client, HTTP_HX_REQUEST="true")
    assert rep.status_code == 200
    html = rep.content.decode()
    assert "<html" not in html and 'id="c-nom-err"' in html
    ok = Client()
    api.surcharges.clear()
    rep = envoyer(ok, HTTP_HX_REQUEST="true")
    assert rep.status_code == 200 and "<html" not in rep.content.decode() and "Message envoyé" in rep.content.decode()


def test_S07_429_affiche_le_delai_et_relaie_retry_after(client, api):
    api.repondre_fixture("contact/", "api_site_contact_limite.json")
    rep = envoyer(client)
    assert rep.status_code == 429 and rep["Retry-After"] == "1800"
    html = rep.content.decode()
    assert "Trop de messages envoyés" in html and "30 minutes" in html and "Jean Mukendi" in html


def test_S07_413_message_trop_volumineux(client, api):
    api.repondre_fixture("contact/", "api_site_contact_trop_gros.json")
    rep = envoyer(client)
    assert rep.status_code == 413
    assert "Message trop volumineux" in rep.content.decode() and "Jean Mukendi" in rep.content.decode()


def test_S07_champ_trop_long_n_atteint_pas_l_api(client, api):
    rep = envoyer(client, {"message": "x" * 3001})
    assert rep.status_code == 400 and "trop long" in rep.content.decode()
    assert not posts(api)


def test_S07_api_coupee_message_clair_et_formulaire_conserve(client, api):
    ouverture = jeton(client.get(URL))
    api.coupee()
    rep = client.post(URL, {**VALIDE, "ouverture": ouverture})
    assert rep.status_code == 503
    html = rep.content.decode()
    assert "Service momentanément indisponible" in html and "Jean Mukendi" in html and "<form" in html
    api.rallumee()
    api.surcharges.clear()
    from django.core.cache import cache

    cache.clear()
    rep = client.post(URL, {**VALIDE, "ouverture": ouverture})  # même jeton : nouvel essai possible
    assert rep.status_code == 200 and "Message envoyé" in rep.content.decode()


def test_S07_application_verrouillee_formulaire_suspendu(client, api):
    api.verrouillee("Maintenance : retour demain.")
    rep = client.get(URL)
    html = rep.content.decode().replace(" ", " ").replace(" ", " ")  # la typographie du site insère des espaces insécables
    assert rep.status_code == 200 and "Service momentanément indisponible" in html and "Maintenance : retour demain." in html
    assert 'name="nom"' not in html
    rep = client.post(URL, {**VALIDE, "ouverture": jeton_valide()})
    assert rep.status_code == 503 and "Service momentanément indisponible" in rep.content.decode()
    assert len([p for p in posts(api) if p[1] == "contact/"]) <= 1  # le verrou connu coupe tout appel de données


@pytest.mark.parametrize("mode", ["inactif", "drapeau"])
def test_S07_mode_exemple_aucun_appel_api_et_contacts_affiches(client, api, mode):
    if mode == "inactif":
        api.inactive()
    else:
        api.config(donnees_reelles=False)
    rep = client.get(URL)
    html = rep.content.decode()
    assert rep.status_code == 200
    assert "Formulaire indisponible pour le moment" in html
    assert 'name="nom"' not in html and "<form" not in html.split('id="contact-zone"')[1].split("</main>")[0]
    assert "mailto:" in html
    rep = client.post(URL, {**VALIDE, "ouverture": "x"})
    assert rep.status_code == 503 and "Formulaire indisponible pour le moment" in rep.content.decode()
    assert not posts(api)


def test_S07_403_inactif_sur_le_depot_bascule_en_mode_exemple(client, api):
    ouverture = jeton(client.get(URL))
    inactif = charger("api_site_inactif.json")["autres"]
    api.repondre("contact/", inactif["status"], inactif["body"])
    rep = client.post(URL, {**VALIDE, "ouverture": ouverture})
    assert "Formulaire indisponible pour le moment" in rep.content.decode()
    assert len(posts(api)) == 1
    rep = client.get(URL)  # le mode est retenu : plus de formulaire
    assert "Formulaire indisponible pour le moment" in rep.content.decode()


def test_S07_limite_par_adresse_ip_a_la_charge_du_site(client, api, settings):
    settings.CONTACT_LIMITE_IP = 3
    for _ in range(3):
        assert envoyer(client).status_code == 200
    rep = envoyer(client)
    assert rep.status_code == 429 and int(rep["Retry-After"]) > 0
    assert "Trop d&#x27;envois" in rep.content.decode() or "Trop d'envois" in rep.content.decode()
    assert len(posts(api)) == 3  # la 4e n'est pas transmise
    autre = envoyer(client, REMOTE_ADDR="10.9.8.7")
    assert autre.status_code == 200 and len(posts(api)) == 4


def test_S07_csrf_exige_sur_le_formulaire(api):
    strict = Client(enforce_csrf_checks=True)
    rep = strict.post(URL, {**VALIDE, "ouverture": "x"})
    assert rep.status_code == 403 and not posts(api)
    page = strict.get(URL)
    assert "csrfmiddlewaretoken" in page.content.decode()


def test_S07_reponse_inattendue_de_l_api_est_traitee_comme_indisponible(client, api):
    api.repondre("contact/", 200, {"quelque": "chose"})
    rep = envoyer(client)
    assert rep.status_code == 503 and "Service momentanément indisponible" in rep.content.decode()


def test_S07_refus_de_cle_api_n_expose_rien_au_visiteur(client, api):
    api.repondre_fixture("contact/", "api_site_cle_invalide.json")
    rep = envoyer(client)
    html = rep.content.decode()
    assert rep.status_code == 503 and "Service momentanément indisponible" in html and "fsk_" not in html


def test_S07_page_contact_sans_api_ne_plante_pas(client, api):
    api.coupee()
    assert client.get(URL).status_code == 200


def test_S07_limite_ip_lit_l_en_tete_reglable(client, api, settings):
    settings.CONTACT_LIMITE_IP = 1
    settings.CONTACT_IP_HEADER = "HTTP_X_REAL_IP"
    assert envoyer(client, HTTP_X_REAL_IP="1.1.1.1").status_code == 200
    assert envoyer(client, HTTP_X_REAL_IP="1.1.1.1").status_code == 429
    assert envoyer(client, HTTP_X_REAL_IP="2.2.2.2").status_code == 200


def test_S07_le_cookie_csrf_est_annonce_dans_les_textes(client):
    assert "csrftoken" in client.get(URL).content.decode()
    assert "csrftoken" in client.get("/confidentialite/").content.decode()
