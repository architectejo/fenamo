"""Aide HTMX commune (cahier des charges web § 6.3).

- ``reponse_succes`` : réponse de fin de formulaire (ferme la modale, affiche un toast,
  déclenche le rafraîchissement des zones concernées).
- ``HtmxSessionMessagesMiddleware`` : session expirée -> ``HX-Redirect`` vers la page
  de connexion ; messages Django -> ``HX-Trigger`` (zone de toasts commune).

Événements reçus par ``static/js/fenamo.js`` :
- ``toast``        : ``{"message": "...", "niveau": "success|danger|warning|info"}``
- ``modaleFermer`` : ferme et vide la modale commune.
Les zones à rafraîchir écoutent leur propre événement, par exemple
``<div hx-get="..." hx-trigger="membresModifies from:body">``.
"""
import json

from django.http import HttpResponse
from django.contrib import messages
from django.urls import reverse
from django.utils.cache import patch_vary_headers

NIVEAUX = {'debug': 'info', 'info': 'info', 'success': 'success', 'warning': 'warning', 'error': 'danger'}


def ajouter_declencheurs(response, declencheurs):
    """Ajoute des événements à l'en-tête ``HX-Trigger`` sans écraser ceux déjà présents."""
    if not declencheurs:
        return response
    actuel = response.headers.get('HX-Trigger')
    evenements = {}
    if actuel:
        try:
            lu = json.loads(actuel)
            evenements = lu if isinstance(lu, dict) else {str(lu): True}
        except ValueError:
            evenements = {nom.strip(): True for nom in actuel.split(',') if nom.strip()}
    for nom, detail in declencheurs.items():
        if nom == 'toast' and 'toast' in evenements:
            # plusieurs toasts : on les regroupe dans une liste
            existant = evenements['toast']
            liste = existant if isinstance(existant, list) else [existant]
            evenements['toast'] = liste + (detail if isinstance(detail, list) else [detail])
        else:
            evenements[nom] = detail
    response.headers['HX-Trigger'] = json.dumps(evenements, ensure_ascii=False)
    return response


def reponse_succes(message=None, niveau='success', evenements=None):
    """Réponse 204 d'un formulaire de modale réussi : ferme la modale, toast, rafraîchissement.

    ``evenements`` : noms d'événements (liste) ou dict ``{nom: détail}`` à émettre pour que les
    zones concernées se rafraîchissent.
    """
    declencheurs = {'modaleFermer': True}
    if message:
        declencheurs['toast'] = {'message': str(message), 'niveau': niveau}
    if isinstance(evenements, dict):
        declencheurs.update(evenements)
    elif evenements:
        declencheurs.update({nom: True for nom in evenements})
    return ajouter_declencheurs(HttpResponse(status=204), declencheurs)


class HtmxSessionMessagesMiddleware:
    """À placer après ``MessageMiddleware`` et ``django_htmx.middleware.HtmxMiddleware``."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        patch_vary_headers(response, ['HX-Request'])
        if not getattr(request, 'htmx', False):
            return response

        if response.status_code in (301, 302, 303, 307, 308):
            adresse = response.headers.get('Location', '').split('?')[0]
            if adresse == reverse('application'):
                # Session expirée : HTMX suivrait la redirection et afficherait la
                # page de connexion dans la zone ciblée ; on redirige la fenêtre entière.
                redirection = HttpResponse(status=200)
                redirection.headers['HX-Redirect'] = response.headers['Location']
                return redirection
            return response  # les messages restent pour la page suivante

        if 'HX-Redirect' in response.headers or 'HX-Location' in response.headers:
            return response
        if hasattr(request, '_messages'):
            declencheurs = [
                {'message': str(m.message), 'niveau': NIVEAUX.get(m.level_tag.split()[0] if m.level_tag else 'info', 'info')}
                for m in messages.get_messages(request)
            ]
            if declencheurs:
                ajouter_declencheurs(response, {'toast': declencheurs if len(declencheurs) > 1 else declencheurs[0]})
        return response
