"""Lot 2a : mode dégradé (S-12), verrou F-07, sonde de santé, purge signée du cache."""
import hashlib
import hmac
import time

import pytest
from django.core.cache import cache

from services import api_client


def vider_copies_fraiches():
    """Simule l'expiration des copies fraîches (les copies de secours restent)."""
    api_client.purger_cache()


# ---------- S-12 : panne ----------

def test_S12_api_coupee_derniere_copie_et_bandeau(client, api):
    assert "bandeau-degrade" not in client.get("/").content.decode()
    api.coupee()
    vider_copies_fraiches()
    cache.delete("api:panne")
    rep = client.get("/")
    html = rep.content.decode()
    assert rep.status_code == 200 and "bandeau-degrade" in html and "Service ralenti." in html
    assert "Les pages affichent les informations du" in html
    assert "Assemblée générale annuelle" in html  # contenu de la copie de secours
    assert "app.fenamordc.cd/media/article/exemple-1.webp" in html


def test_S12_la_copie_servie_n_est_pas_renouvelee(api):
    from services import site_api

    api_client.demarrer_suivi()
    site_api.config()
    avant = cache.get(api_client._STALE + api_client._cle("config/", None, None))
    api.coupee()
    vider_copies_fraiches()
    site_api.config()
    apres = cache.get(api_client._STALE + api_client._cle("config/", None, None))
    assert apres["t"] == avant["t"]
    assert api_client.suivi()["degrade"] is True


def test_S12_delai_depasse_meme_comportement(client, api):
    client.get("/")
    api.mode = "lente"
    vider_copies_fraiches()
    assert "bandeau-degrade" in client.get("/").content.decode()


def test_S12_cle_refusee_ou_limite_donnent_la_copie(client, api):
    client.get("/")
    vider_copies_fraiches()
    api.repondre("articles/", 429, {"detail": "Trop de requêtes."})
    api.repondre("config/", 401, {"detail": "Clé du site absente ou invalide."})
    rep = client.get("/")
    assert rep.status_code == 200 and "bandeau-degrade" in rep.content.decode()


def test_S12_api_coupee_sans_copie_etat_vide_soigne(client, api):
    api.coupee()
    html = client.get("/").content.decode()
    assert "Les actualités ne sont pas disponibles pour le moment" in html
    assert "chiffres de la fédération ne sont pas disponibles" in html
    assert "Unité, Discipline et Progrès" in html  # pied de page : valeurs de repli


def test_S12_panne_recente_evite_les_attentes_en_cascade(client, api):
    api.coupee()
    client.get("/")
    nb = len(api.appels)
    client.get("/")
    assert len(api.appels) == nb  # les lectures suivantes n'attendent pas 5 s de plus chacune


# ---------- F-07 : verrou ----------

def test_F07_verrou_distinct_d_une_panne_copie_servie_sans_journal_d_erreur(client, api, caplog):
    client.get("/")
    vider_copies_fraiches()
    api.verrouillee("Maintenance : retour demain.")
    with caplog.at_level("WARNING"):
        rep = client.get("/")
    html = rep.content.decode()
    assert rep.status_code == 200 and "Plateforme momentanément fermée." in html and "Service ralenti." not in html
    assert not [r for r in caplog.records if r.levelname in ("WARNING", "ERROR")]


def test_F07_le_503_n_est_jamais_mis_en_cache_comme_contenu(client, api):
    api.verrouillee()
    html = client.get("/").content.decode()
    assert "Maintenance" not in html  # le message n'est affiché que sur les pages de fonctions suspendues
    assert cache.get(api_client._STALE + api_client._cle("config/", None, None)) is None


def test_F07_verifier_affiche_le_message_echappe(client, api):
    api.verrouillee("<b>Retour</b> à 14 h\nMerci")
    rep = client.get("/verifier/")
    html = rep.content.decode()
    assert rep.status_code == 503 and "Service suspendu" in html and "message-su" in html
    assert "&lt;b&gt;Retour&lt;/b&gt;" in html and "<b>Retour</b>" not in html
    assert "disabled" in html and "noindex" in html


def test_F07_pas_d_appel_de_donnees_pendant_le_verrou_une_sonde_par_intervalle(client, api, settings):
    api.verrouillee()
    client.get("/verifier/")
    donnees = len(api.appels_donnees())
    for _ in range(5):
        client.get("/verifier/")
    assert len(api.appels_donnees()) == donnees
    assert api.sondes == 0  # intervalle (30 s) pas encore écoulé


def test_F07_sonde_apres_intervalle_puis_reprise_a_la_fin_du_verrou(client, api, settings):
    api.verrouillee()
    client.get("/verifier/")
    etat = cache.get(api_client._ETAT)
    etat["sonde"] -= settings.API_SANTE_INTERVALLE + 1
    cache.set(api_client._ETAT, etat, 600)
    client.get("/verifier/")
    assert api.sondes == 1  # toujours suspendu : une seule sonde
    api.deverrouillee()
    etat = cache.get(api_client._ETAT)
    etat["sonde"] -= settings.API_SANTE_INTERVALLE + 1
    cache.set(api_client._ETAT, etat, 600)
    rep = client.get("/verifier/")
    assert api.sondes == 2 and cache.get(api_client._ETAT) is None
    assert rep.status_code == 200 and "Service suspendu" not in rep.content.decode()


def test_F07_adresse_de_sante_derivee_ou_reglee(settings):
    settings.API_BASE_URL = "https://app.example.invalid/api/v1/site/"
    settings.API_SANTE_URL = ""
    assert api_client.url_sante() == "https://app.example.invalid/api/v1/sante/"
    settings.API_SANTE_URL = "https://autre.example.invalid/sante/"
    assert api_client.url_sante() == "https://autre.example.invalid/sante/"


def test_F07_503_sans_statut_suspendu_reste_une_panne(client, api):
    client.get("/")
    vider_copies_fraiches()
    api.repondre("config/", 503, {"detail": "Service indisponible"})
    rep = client.get("/")
    assert "Service ralenti." in rep.content.decode()
    assert cache.get(api_client._ETAT) is None


# ---------- purge ----------

SECRET = "secret-de-test-purge"


def signer(horodatage, secret=SECRET):
    return hmac.new(secret.encode(), str(horodatage).encode(), hashlib.sha256).hexdigest()


def appeler(client, horodatage=None, signature=None, **kw):
    horodatage = int(time.time()) if horodatage is None else horodatage
    signature = signer(horodatage) if signature is None else signature
    return client.post("/_purge/", HTTP_X_PURGE_TIMESTAMP=str(horodatage), HTTP_X_PURGE_SIGNATURE=signature, **kw)


@pytest.fixture
def secret(settings):
    settings.PURGE_SECRET = SECRET


def test_purge_signature_acceptee_vide_les_copies_fraiches_garde_les_copies_de_secours(client, api, secret):
    client.get("/actualites/")
    nb = len(api.appels)
    client.get("/actualites/")
    assert len(api.appels) == nb  # servi par le cache
    assert appeler(client).status_code == 204
    client.get("/actualites/")
    assert len(api.appels) > nb  # copies fraîches vidées
    assert cache.get(api_client._STALE + api_client._cle("config/", None, None)) is not None


def test_purge_en_tete_horodatage_de_web_app(client, secret):
    horodatage = int(time.time())
    rep = client.post("/_purge/", HTTP_X_PURGE_HORODATAGE=str(horodatage), HTTP_X_PURGE_SIGNATURE=signer(horodatage))
    assert rep.status_code == 204


def test_purge_signature_refusee(client, secret):
    assert appeler(client, signature="0" * 64).status_code == 403
    assert appeler(client, signature=signer(int(time.time()), secret="autre")).status_code == 403
    assert client.post("/_purge/").status_code == 403
    assert client.post("/_purge/", HTTP_X_PURGE_TIMESTAMP="abc", HTTP_X_PURGE_SIGNATURE="x").status_code == 403


def test_purge_sans_secret_configure_toujours_refusee(client, settings):
    settings.PURGE_SECRET = ""
    assert appeler(client, signature=signer(int(time.time()), secret="")).status_code == 403


def test_purge_horodatage_hors_tolerance_refuse(client, secret):
    assert appeler(client, horodatage=int(time.time()) - 301).status_code == 403
    assert appeler(client, horodatage=int(time.time()) + 301).status_code == 403
    assert appeler(client, horodatage=int(time.time()) - 299).status_code == 204


def test_purge_rejouee_refusee(client, secret):
    horodatage = int(time.time())
    assert appeler(client, horodatage=horodatage).status_code == 204
    assert appeler(client, horodatage=horodatage).status_code == 403


def test_purge_limite_de_dix_appels_par_minute(client, secret):
    codes = [appeler(client, signature="0" * 64).status_code for _ in range(11)]
    assert codes[:10] == [403] * 10 and codes[10] == 429


def test_purge_methode_et_csrf(secret):
    from django.test import Client

    csrf = Client(enforce_csrf_checks=True)
    assert csrf.get("/_purge/").status_code == 405
    assert appeler(csrf).status_code == 204  # exemptée de CSRF : l'appelant s'authentifie par signature
