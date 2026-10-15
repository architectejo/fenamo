"""Intergiciels du site : suivi de l'API par requête (S-12) et langues inactives (§ 7)."""
from django.conf import settings
from django.http import HttpResponseRedirect

from services import api_client, langues


class SuiviApiMiddleware:
    """Remet à zéro, à chaque requête, ce que la page doit signaler du mode dégradé (copie, verrou, panne)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        api_client.demarrer_suivi()
        return self.get_response(request)


class LangueInactiveMiddleware:
    """Redirige (302) /<code>/... vers la version française si <code> n'est pas actif.

    Placé avant LocaleMiddleware. Réversible : activer la langue (configuration de l'API ou ACTIVE_LANGUAGES
    en repli) suffit à rendre son préfixe à nouveau servi. N'interroge la configuration que pour un préfixe
    de langue connu autre que le français.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        segments = request.path_info.split("/", 2)
        if len(segments) > 1:
            code = segments[1]
            connus = {c for c, _n in settings.LANGUAGES}
            if code in connus and code != settings.LANGUAGE_CODE and code not in langues.langues_actives():
                reste = segments[2] if len(segments) > 2 else ""
                cible = "/" + reste
                if request.META.get("QUERY_STRING"):
                    cible += "?" + request.META["QUERY_STRING"]
                return HttpResponseRedirect(cible)
        return self.get_response(request)
