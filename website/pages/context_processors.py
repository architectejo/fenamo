from django.conf import settings
from django.urls import translate_url


def site(request):
    """Variables communes : langues actives, hreflang, noindex global."""
    path = request.path
    active = [(c, n) for c, n in settings.LANGUAGES if c in settings.ACTIVE_LANGUAGES]
    # Sélecteur et hreflang : langues actives seulement (une langue inactive redirige vers le français).
    return {
        "site_url": settings.SITE_URL,
        "site_noindex": settings.SITE_NOINDEX,
        "show_language_switcher": len(active) > 1,
        "language_links": [(c, n, translate_url(path, c)) for c, n in active],
        "hreflang_alternates": [
            (c, settings.SITE_URL + translate_url(path, c)) for c, _n in active
        ],
        "hreflang_default": settings.SITE_URL + translate_url(path, settings.LANGUAGE_CODE),
        "canonical_url": settings.SITE_URL + path,
    }
