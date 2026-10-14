"""Formulaires d'ajout et de modification servis dans la modale commune (règle : tout formulaire passe par la modale).

Une vue qui rendait une page (``render(request, 'app/add-xxx.html', locals())``) appelle ``rendre_formulaire`` : pour une requête HTMX
(hors navigation boostée) elle répond la modale ``app/modales/_xxx.html`` ; la page complète reste le repli sans JavaScript.

- GET : la modale ;
- POST refusé (statut 400, ou message d'erreur) : la même modale, statut 422, saisie conservée ;
- POST réussi (message de succès) : le message part en toast après rechargement de la page d'origine (``HX-Refresh``) ;
- ``lecture_unique=True`` : le succès (mot de passe temporaire) est affiché dans la modale, jamais mis en message ni en session ;
- redirection d'une vue (succès) : convertie en ``HX-Redirect`` par le middleware HTMX.
"""
from django.contrib import messages as contrib_messages
from django.http import HttpResponse
from django.shortcuts import render

from fenamo.htmx import veut_fragment


PAGES = {'famille': 'app/add-family.html'}  # nom de la modale -> page de repli quand le nom diffère


def niveau_message(classe):
    """'succes' pour les classes héritées alert-success / alert-info / alert-primary, 'danger' sinon."""
    classe = classe or ''
    return 'succes' if any(mot in classe for mot in ('success', 'info', 'primary')) else 'danger'


def rendre_formulaire(request, nom, contexte, status=200, lecture_unique=False, page=None):
    """Rend la page ``app/add-<nom>.html`` ou, pour HTMX, la modale ``app/modales/_<nom>.html`` (voir le module)."""
    if not veut_fragment(request):
        return render(request, page or PAGES.get(nom, f'app/add-{nom}.html'), contexte, status=status)
    message = contexte.get('message')
    classe = contexte.get('classe') or contexte.get('classMsg') or contexte.get('classMessage') or ''
    if request.method == 'POST' and status < 400 and message and niveau_message(classe) == 'succes':
        if lecture_unique:
            # Le message contient un mot de passe temporaire : jamais en message flash ni en session, affiché une fois dans la réponse.
            reponse = render(request, f'app/modales/_{nom}.html', {**contexte, 'succes': str(message), 'action': request.get_full_path()})
            reponse['Cache-Control'] = 'no-store, private'
            return reponse
        contrib_messages.success(request, str(message))
        reponse = HttpResponse(status=200)
        reponse['HX-Refresh'] = 'true'
        return reponse
    erreur = str(message) if message and (status >= 400 or niveau_message(classe) == 'danger') else ''
    contexte = {**contexte, 'erreur': erreur, 'action': request.get_full_path(), 'multipart': True}
    return render(request, f'app/modales/_{nom}.html', contexte, status=422 if (status >= 400 or erreur) else 200)
