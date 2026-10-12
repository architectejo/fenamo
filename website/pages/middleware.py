"""Langues inactives : leur préfixe ne sert pas de contenu dupliqué (§ 7)."""
from django.conf import settings
from django.http import HttpResponseRedirect


class LangueInactiveMiddleware:
    """Redirige (302) /<code>/... vers la version française si <code> n'est pas actif.

    Placé avant LocaleMiddleware. Réversible : activer la langue (ACTIVE_LANGUAGES)
    suffit à rendre son préfixe à nouveau servi.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        segments = request.path_info.split("/", 2)
        if len(segments) > 1:
            code = segments[1]
            connus = {c for c, _n in settings.LANGUAGES}
            if code in connus and code != settings.LANGUAGE_CODE and code not in settings.ACTIVE_LANGUAGES:
                reste = segments[2] if len(segments) > 2 else ""
                cible = "/" + reste
                if request.META.get("QUERY_STRING"):
                    cible += "?" + request.META["QUERY_STRING"]
                return HttpResponseRedirect(cible)
        return self.get_response(request)
