from django.conf.urls.i18n import i18n_patterns
from django.urls import include, path

# Français sans préfixe ; ln, sw, lua, kg avec préfixe. Les textes sources sont
# en français : un texte non traduit s'affiche donc en français (repli).
urlpatterns = i18n_patterns(
    path("", include("pages.urls")),
    prefix_default_language=False,
)
