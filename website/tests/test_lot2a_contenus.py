"""Lot 2a : contenus des pages, recherche HTMX, référencement, typographie, erreurs, téléchargements."""
import importlib

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import clear_url_caches

from tests.test_lot2a_pages import PAGES


# ---------- contenus ----------

def test_S09_accueil_chiffres_sans_engins_tant_que_l_api_les_masque(client):
    html = client.get("/").content.decode()
    assert "membres actifs" in html and "associations membres" in html
    assert "engins identifiés" not in html  # engins_actifs = null dans l'API


def test_S09_accueil_affiche_les_engins_quand_l_api_les_fournit(client, api):
    api._statistiques["engins_actifs"] = 1234
    assert "engins identifiés" in client.get("/").content.decode()


def test_S01_accueil_formulaire_de_verification_en_get(client):
    html = client.get("/").content.decode()
    assert 'action="/verifier/" method="get"' in html and 'name="numero"' in html


def test_S01_comite_ordre_des_editeurs_et_fonctions_de_la_charte(client):
    html = client.get("/organisation/comite/").content.decode()
    assert html.index("Nom Exemple") < html.index("Autre Exemple")
    assert "Président national" in html and "Commissaires aux comptes" in html


def test_S01_coordinations_carte_et_liste(client, api):
    api._coordinations[0]["code"] = "KN-E"
    html = client.get("/organisation/coordinations/").content.decode()
    assert 'id="coord-KN-E"' in html and 'href="#coord-KN-E"' in html and "Gombe" in html
    assert 'href="#coord-KC"' in html or 'details class="coord" id="coord-KC"' in html
    assert 'href="#coord-KC"' in html  # KC figure dans les positions de la carte


def test_S01_coordinations_code_inconnu_de_la_carte_reste_dans_la_liste(client):
    html = client.get("/organisation/coordinations/").content.decode()
    assert 'id="coord-KIN"' in html and 'href="#coord-KIN"' not in html


def test_S01_documents_groupes_et_lien_de_telechargement_du_site(client):
    html = client.get("/documents/").content.decode()
    assert "/telecharger/document/charte/" in html and "app.fenamordc.cd/media" not in html


def test_S01_application_version_et_telechargement(client):
    html = client.get("/application/").content.decode()
    assert "1.0.0" in html and "/telecharger/application/fenamo-1-0-0/" in html


def test_S01_application_absente_etat_vide(client, api):
    api.config(application=None)
    assert "pas encore disponible" in client.get("/application/").content.decode()


def test_S01_pas_de_montant_invente_pour_l_adhesion(client):
    for chemin in ("/", "/adhesion/"):
        assert " FC" not in client.get(chemin).content.decode()


def test_S01_contact_n_affiche_que_ce_que_donne_la_config(client, api):
    html = client.get("/contact/").content.decode()
    assert "contact@fenamordc.cd" in html and "+243 800 000 001" in html
    api.config(telephones=[], email="")
    cache.clear()
    html = client.get("/contact/").content.decode()
    assert 'href="tel:' not in html and "mailto:" not in html  # le formulaire (S-07) reste, les coordonnées absentes disparaissent


def test_S01_carte_google_seulement_avec_une_cle(client, settings):
    assert "data-carte-charger" not in client.get("/contact/").content.decode()
    settings.GOOGLE_MAPS_KEY = "cle-de-test"
    html = client.get("/contact/").content.decode()
    assert "data-carte-charger" in html and "key=cle-de-test" in html


# ---------- actualités ----------

def test_S02_recherche_htmx_renvoie_le_fragment(client):
    rep = client.get("/actualites/?q=assemblée", HTTP_HX_REQUEST="true")
    html = rep.content.decode()
    assert "<html" not in html and "Assemblée" in html and "<mark>" in html
    assert "HX-Request" in rep["Vary"]


def test_S02_recherche_page_complete_et_etat_vide(client):
    assert "<html" in client.get("/actualites/?q=assemblée").content.decode()
    html = client.get("/actualites/?q=zzzz", HTTP_HX_REQUEST="true").content.decode()
    assert "Aucun article ne contient" in html


def test_S02_filtre_par_type(client):
    html = client.get("/actualites/?type=communique").content.decode()
    assert "Assemblée générale annuelle" in html and "Nouvelle campagne" not in html


def test_S02_page_hors_limite_404(client):
    assert client.get("/actualites/?page=9").status_code == 404


def test_S01_article_inconnu_404(client):
    assert client.get("/actualites/inconnu/").status_code == 404


def test_S01_article_texte_nettoye_une_seconde_fois(client, api):
    api._detail["texte"] = (
        '<p onclick="x()">Bonjour <a href="javascript:alert(1)">lien</a></p><script>alert(1)</script>'
        '<img src=x onerror=alert(1)><a href="https://ok.example">ok</a>'
    )
    html = client.get("/actualites/assemblee-generale-annuelle/").content.decode()
    assert "<script>alert" not in html and "onerror" not in html and "onclick" not in html and "javascript:" not in html
    assert "Bonjour" in html and 'href="https://ok.example" rel="noopener noreferrer"' in html


def test_S01_article_video_construite_depuis_fournisseur_et_identifiant(client, api):
    html = client.get("/actualites/assemblee-generale-annuelle/").content.decode()
    assert "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ" in html and "<iframe" not in html
    api._detail["video"] = {"fournisseur": "youtube", "identifiant": '"><script>x</script>'}
    from django.core.cache import cache

    cache.clear()
    html = client.get("/actualites/assemblee-generale-annuelle/").content.decode()
    assert "<script>x" not in html and "lecteur-video-lien" not in html


def test_S01_article_video_facebook_hote_verifie():
    from services.nettoyage import construire_video

    assert construire_video({"fournisseur": "facebook", "identifiant": "https://www.facebook.com/x/videos/1"})["embed"].startswith("https://www.facebook.com/plugins/")
    assert construire_video({"fournisseur": "facebook", "identifiant": "https://evil.example/x"}) is None
    assert construire_video({"fournisseur": "vimeo", "identifiant": "12345678901"}) is None


def test_S08_article_open_graph_et_partage(client):
    html = client.get("/actualites/assemblee-generale-annuelle/").content.decode()
    assert 'property="og:type" content="article"' in html
    assert 'property="og:image" content="https://app.fenamordc.cd/media/article/exemple-1.webp"' in html
    assert "wa.me" in html and "facebook.com/sharer" in html and "twitter.com/intent" in html and "data-copier-lien" in html


def test_S01_article_mention_de_langue_si_non_traduit(client, api, langues_completes):
    api.config(langues_actives=["fr", "ln"])
    api._detail["traduit"] = False
    html = client.get("/ln/actualites/assemblee-generale-annuelle/").content.decode()
    assert "mention-langue" in html and "lingala" in html


def test_S01_galerie_photos_et_videos(client):
    html = client.get("/galerie/").content.decode()
    assert "data-visionneuse" in html and 'data-src="https://app.fenamordc.cd/media/article/exemple-1.webp"' in html
    assert "youtube-nocookie.com/embed/dQw4w9WgXcQ" in html and 'id="visionneuse"' in html


# ---------- référencement ----------

def test_S08_titre_description_og_par_page(client):
    for chemin in PAGES:
        html = client.get(chemin).content.decode()
        assert "<title>" in html and 'name="description"' in html and 'property="og:title"' in html
        assert f'rel="canonical" href="http://localhost:8001{chemin}"' in html


def test_S11_hreflang_sur_chaque_page_avec_deux_langues(client, api, langues_completes):
    api.config(langues_actives=["fr", "ln"])
    html = client.get("/a-propos/").content.decode()
    assert 'hreflang="fr" href="http://localhost:8001/a-propos/"' in html
    assert 'hreflang="ln" href="http://localhost:8001/ln/a-propos/"' in html
    assert 'hreflang="x-default"' in html


def test_sitemap_et_robots(client):
    xml = client.get("/sitemap.xml").content.decode()
    assert "<loc>http://localhost:8001/a-propos/</loc>" in xml and "assemblee-generale-annuelle" in xml
    robots = client.get("/robots.txt").content.decode()
    assert "Sitemap: http://localhost:8001/sitemap.xml" in robots and "Disallow: /verifier/" in robots and "/_purge/" in robots


def test_sitemap_langues_actives_avec_alternates(client, api, langues_completes):
    api.config(langues_actives=["fr", "ln"])
    assert 'hreflang="ln" href="http://localhost:8001/ln/a-propos/"' in client.get("/sitemap.xml").content.decode()


def test_robots_noindex_total(client, settings):
    settings.SITE_NOINDEX = True
    assert "Disallow: /\n" in client.get("/robots.txt").content.decode()


@pytest.mark.parametrize(
    "ancienne,nouvelle",
    [
        ("/a-propos-de-nous/", "/a-propos/"), ("/activites/", "/actualites/"), ("/article-by-coptam-rdc/12", "/actualites/"),
        ("/portail/", "/"), ("/confidentiel/", "/confidentialite/"),
    ],
)
def test_redirections_301_des_anciennes_adresses(client, ancienne, nouvelle):
    rep = client.get(ancienne)
    assert rep.status_code == 301 and rep["Location"] == nouvelle


def test_ancienne_configuration_410(client):
    assert client.get("/configuration/").status_code == 410


# ---------- typographie, interdits, poids ----------

def test_typographie_francaise():
    from pages.templatetags.site_tags import typographie

    assert typographie("<p>Voir : « ceci » ! Vraiment ?</p>") == "<p>Voir : « ceci » ! Vraiment ?</p>"
    sortie = typographie('<p title="a : b">La FENAMO-RDC</p><option>FENAMO-RDC</option>')
    assert 'title="a : b"' in sortie and 'La <bdi class="insecable">FENAMO-RDC</bdi>' in sortie and "<option>FENAMO-RDC</option>" in sortie


def test_pas_de_mention_de_l_ancien_nom(client):
    for chemin in PAGES:
        assert "COPTAM" not in client.get(chemin).content.decode().upper()


def test_S01_poids_de_l_accueil_sous_600_ko(client):
    """HTML + feuilles + script + sprite + logo + polices de l'accueil (sans photos de l'API)."""
    from django.conf import settings

    total = len(client.get("/").content)
    racine = settings.BASE_DIR / "static"
    for fichier in (
        "css/tokens.css", "css/site.css", "js/site.js", "js/theme.js", "img/icons.svg", "img/logo-160.webp", "img/favicon.png",
        "fonts/atkinson-hyperlegible-next-400.woff2", "fonts/barlow-condensed-600.woff2",
    ):
        total += (racine / fichier).stat().st_size
    assert total < 600 * 1024, total


# ---------- erreurs ----------

def test_404_page_sobre_avec_retour_accueil(client):
    rep = client.get("/page-inconnue/")
    html = rep.content.decode()
    assert rep.status_code == 404 and "Retour à l'accueil" in html and "noindex" in html


def test_500_rendu_sans_appel_a_l_api(api):
    from django.test import RequestFactory

    from pages.views import page_500

    rep = page_500(RequestFactory().get("/"))
    assert rep.status_code == 500 and b"Le site rencontre un probl" in rep.content and api.appels == []


def test_500_vue_qui_plante_donne_la_page_autonome(api, monkeypatch):
    import pages.views as vues

    def boum(request):
        raise RuntimeError("panne interne")

    monkeypatch.setattr(vues, "contact", boum)
    importlib.reload(importlib.import_module("pages.urls"))
    importlib.reload(importlib.import_module("site_fenamo.urls"))
    clear_url_caches()
    try:
        api.coupee()
        rep = Client(raise_request_exception=False).get("/contact/")
        assert rep.status_code == 500 and "Le site rencontre un probl" in rep.content.decode()
    finally:
        monkeypatch.undo()
        importlib.reload(importlib.import_module("pages.urls"))
        importlib.reload(importlib.import_module("site_fenamo.urls"))
        clear_url_caches()


# ---------- téléchargements (S-10) ----------

def test_S10_telechargement_compte_puis_redirige(client):
    from pages.models import Telechargement

    rep = client.get("/telecharger/document/charte/")
    assert rep.status_code == 302 and rep["Location"] == "https://app.fenamordc.cd/media/documents/exemple-3.pdf"
    client.get("/telecharger/document/charte/")
    assert Telechargement.objects.get(cle="document:charte").total == 2
    assert "2 téléchargements" in client.get("/documents/").content.decode()
    assert client.get("/telecharger/application/fenamo-1-0-0/")["Location"].endswith("exemple-4.apk")


def test_S10_telechargement_inconnu_404_et_post_refuse(client):
    assert client.get("/telecharger/document/inconnu/").status_code == 404
    assert client.get("/telecharger/autre/x/").status_code == 404
    assert client.post("/telecharger/document/charte/").status_code == 405
