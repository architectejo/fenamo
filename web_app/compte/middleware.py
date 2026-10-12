"""Changement de mot de passe imposé à la première connexion (compte créé par un super-utilisateur)."""
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse


class ChangementMotDePasseMiddleware:
    """À placer après AuthenticationMiddleware et HtmxMiddleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and getattr(user, 'doit_changer_mot_de_passe', False):
            libres = (reverse('securite'), reverse('deconnexion'))
            chemin = request.path
            if chemin not in libres and not chemin.startswith(reverse('securite')) and not chemin.startswith('/static/'):
                if chemin.startswith('/api/'):
                    return JsonResponse({'detail': 'Changement de mot de passe requis.'}, status=403)
                cible = reverse('securite')
                if getattr(request, 'htmx', False):
                    reponse = HttpResponse(status=200)
                    reponse.headers['HX-Redirect'] = cible
                    return reponse
                return redirect(cible)
        return self.get_response(request)
