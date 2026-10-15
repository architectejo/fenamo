"""Changement de mot de passe imposé à la première connexion (compte créé par un super-utilisateur)."""
from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import add_never_cache_headers


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


class VerrouApplicationMiddleware:
    """Verrouillage de l'application (F-07), vérifié à CHAQUE requête (lecture en base, aucun cache).

    À placer après HtmxSessionMessagesMiddleware et avant LoginRequiredMiddleware. Verrouillée : le super-utilisateur connecté passe
    partout ; les fichiers statiques, /connexion/, /deconnexion/ et /gestion-technique/ passent toujours (la vue de connexion refuse
    les comptes non SU) ; tout autre visiteur est refusé : sa session est fermée, puis la réponse dépend du chemin (API : 503 JSON,
    sauf la vue de santé ; /mob/ : 503 HTML et session mobile vidée ; HTMX : redirection vers /connexion/ ; sinon page 503).
    Les réponses n'exposent que le message du super-utilisateur (jamais le motif, l'auteur ni la date) et ne se mettent pas en cache."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from compte.services import verrou_application as verrou
        courant = verrou.etat()
        if not courant.verrouillee or verrou.chemin_exempte(request.path):
            return self.get_response(request)
        user = request.user
        if user.is_authenticated and user.is_active and user.is_superuser:
            return self.get_response(request)
        if user.is_authenticated:
            logout(request)  # la session ouverte est fermée à la requête suivante, pas seulement bloquée
        return self._refuser(request, courant.message)

    def _refuser(self, request, message):
        chemin = request.path
        if chemin.startswith('/api/'):
            if chemin.rstrip('/') == '/api/v1/sante':
                reponse = JsonResponse({'statut': 'suspendu', 'version': 'v1'})  # 200 : on distingue un verrou d'une panne
            else:
                reponse = JsonResponse({'statut': 'suspendu', 'detail': 'Service suspendu.', 'message': message}, status=503)
        elif chemin.startswith('/mob/'):
            for cle in ('mob_membre_id', 'mob_empreinte'):
                request.session.pop(cle, None)
            reponse = render(request, 'mob/suspendu.html', {'message': message}, status=503)
        elif getattr(request, 'htmx', False):
            reponse = HttpResponse(status=200)
            reponse.headers['HX-Redirect'] = reverse('application')
        else:
            reponse = render(request, '503.html', {'message': message}, status=503)
        add_never_cache_headers(reponse)
        reponse.headers['Cache-Control'] = 'no-store'
        return reponse
