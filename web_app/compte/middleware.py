"""Changement de mot de passe imposé à la première connexion (compte créé par un super-utilisateur)."""
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse


class ChangementMotDePasseMiddleware:
    """À placer après AuthenticationMiddleware et HtmxMiddleware."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.url_securite = reverse('securite')
        self.url_deconnexion = reverse('deconnexion')
        self.prefixe_statique = '/' + settings.STATIC_URL.strip('/') + '/'

    def __call__(self, request):
        user = request.user
        if not (user.is_authenticated and getattr(user, 'doit_changer_mot_de_passe', False)):
            return self.get_response(request)
        chemin = request.path
        if chemin in (self.url_securite, self.url_deconnexion) or chemin.startswith(self.prefixe_statique):
            return self.get_response(request)
        if chemin.startswith('/api/'):
            return JsonResponse({'detail': 'Changement de mot de passe requis.'}, status=403)
        if getattr(request, 'htmx', False):
            reponse = HttpResponse(status=200)
            reponse.headers['HX-Redirect'] = self.url_securite
            return reponse
        return redirect(self.url_securite)
