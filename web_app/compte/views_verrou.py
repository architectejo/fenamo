"""Verrouillage de l'application (F-07) : écran et modales, super-utilisateur seul (``superuser_requis``), POST + CSRF."""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from compte.permissions import superuser_requis
from compte.services import verrou_application as verrou
from fenamo.htmx import reponse_succes, veut_fragment

EVENEMENT = 'verrouModifie'


@require_GET
@superuser_requis
@never_cache
def verrou_application(request):
    """Écran de l'état : verrouillée ou non, message, depuis quand, par qui (visible du seul super-utilisateur). Fragment HTMX : la zone d'état
    seule, avec la classe « change » (animation « tampon ») : elle n'est demandée qu'après un changement d'état."""
    contexte = verrou.contexte_etat(verrou.etat())
    if veut_fragment(request):
        return render(request, 'compte/partials/_verrou_zone.html', {**contexte, 'change': True})
    return render(request, 'compte/verrou_application.html', contexte)


def _terminer(request, message):
    if request.htmx:
        return reponse_succes(message, evenements=[EVENEMENT])
    messages.success(request, message)
    return redirect('verrou-application')


@require_http_methods(['GET', 'POST'])
@superuser_requis
def verrouiller(request):
    etat_courant = verrou.etat()
    _su, hors_su = verrou.sessions_ouvertes()
    contexte = {'action': request.path, 'message_max': verrou.MESSAGE_MAX, 'motif_max': verrou.MOTIF_MAX, 'etat': etat_courant, 'sessions_hors_su': hors_su}
    if request.method == 'GET':
        return render(request, 'compte/partials/_modale_verrouiller.html', contexte)
    message, motif = (request.POST.get('message') or '').strip(), (request.POST.get('motif') or '').strip()
    try:
        verrou.verrouiller(request.user, message, motif)
    except verrou.RegleVerrou as erreur:
        return render(request, 'compte/partials/_modale_verrouiller.html', {**contexte, ('erreur_message' if (not message or len(message) > verrou.MESSAGE_MAX) else 'erreur_motif'): str(erreur), 'valeur_message': message,
                                                                           'valeur_motif': motif}, status=422)
    return _terminer(request, _("Application verrouillée"))


@require_http_methods(['GET', 'POST'])
@superuser_requis
def deverrouiller(request):
    etat_courant = verrou.etat()
    contexte = {'action': request.path, 'motif_max': verrou.MOTIF_MAX, 'etat': etat_courant,
                'duree': verrou.duree_en_texte(timezone.now() - etat_courant.depuis) if etat_courant.depuis else ''}
    if request.method == 'GET':
        return render(request, 'compte/partials/_modale_deverrouiller.html', contexte)
    try:
        verrou.deverrouiller(request.user, (request.POST.get('motif') or '').strip())
    except verrou.RegleVerrou as erreur:
        return render(request, 'compte/partials/_modale_deverrouiller.html', {**contexte, 'erreur': str(erreur)}, status=422)
    return _terminer(request, _("Application déverrouillée"))
