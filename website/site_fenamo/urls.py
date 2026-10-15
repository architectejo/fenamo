from django.conf.urls.i18n import i18n_patterns
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from pages import views

handler404 = "pages.views.page_404"
handler500 = "pages.views.page_500"

# Hors préfixe de langue : purge, sitemap, robots et anciennes adresses du site « virtrine » (annexe B)
urlpatterns = [
    path("_purge/", views.purge, name="purge"),
    path("sitemap.xml", views.sitemap, name="sitemap"),
    path("robots.txt", views.robots, name="robots"),
    path("a-propos-de-nous/", RedirectView.as_view(url="/a-propos/", permanent=True)),
    path("activites/", RedirectView.as_view(url="/actualites/", permanent=True)),
    re_path(r"^article-by-coptam-rdc/(?P<ancien_id>[^/]+)/?$", RedirectView.as_view(url="/actualites/", permanent=True)),
    path("portail/", RedirectView.as_view(url="/", permanent=True)),
    path("confidentiel/", RedirectView.as_view(url="/confidentialite/", permanent=True)),
    path("configuration/", views.ancienne_adresse_supprimee),
]

# Français sans préfixe ; ln, sw, lua, kg avec préfixe. Les textes sources sont
# en français : un texte non traduit s'affiche donc en français (repli).
urlpatterns += i18n_patterns(
    path("", include("pages.urls")),
    prefix_default_language=False,
)
