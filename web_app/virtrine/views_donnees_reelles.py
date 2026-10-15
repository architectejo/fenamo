"""Interrupteur « données réelles » du site public : super-utilisateur seul, POST + CSRF (modale de confirmation)."""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods

from compte.permissions import superuser_requis
from fenamo.htmx import reponse_succes
from virtrine.services import contenu
from virtrine.services.etat_donnees_reelles import etat_donnees_reelles

EVENEMENT = 'donneesReellesModifiees'


@require_http_methods(['GET', 'POST'])
@superuser_requis
def donnees_reelles(request):
    """GET : modale de confirmation. POST ``actif`` (1 pour afficher les données réelles, 0 pour le jeu d'exemple) et ``motif`` facultatif.

    Contexte de la modale : action, actif (état actuel), cible (état demandé), motif_max, erreur. HTMX : 204 + toast + événement
    ``donneesReellesModifiees`` ; sinon message et retour à l'écran du contenu du site."""
    actuel = etat_donnees_reelles()['actif']  # lecture seule : un GET ne crée jamais la ligne de configuration
    contexte = {'action': request.path, 'actif': actuel, 'cible': not actuel, 'motif_max': contenu.MOTIF_MAX}
    if request.method == 'GET':
        return render(request, 'virtrine/partials/_modale_donnees_reelles.html', contexte)
    voulu = (request.POST.get('actif') or '').strip().lower() in ('1', 'true', 'on', 'oui')
    try:
        contenu.definir_donnees_reelles(request.user, voulu, request.POST.get('motif', ''))
    except ValidationError as erreur:
        return render(request, 'virtrine/partials/_modale_donnees_reelles.html', {**contexte, 'erreur': ' '.join(erreur.messages)}, status=422)
    detail = _("Le site affiche maintenant les données réelles.") if voulu else _("Le site affiche maintenant son jeu d'exemple.")
    message = _("Données réelles activées") if voulu else _("Données d'exemple rétablies")
    if request.htmx:
        return reponse_succes(message, evenements=[EVENEMENT], detail=detail)
    messages.success(request, detail)
    return redirect('site')


@require_GET
@superuser_requis
def donnees_reelles_etat(request):
    """Fragment de la carte d'état (rafraîchi par l'événement ``donneesReellesModifiees``) : une seule source de HTML avec l'écran Contenu du site."""
    return render(request, 'virtrine/partials/_donnees_reelles.html', {'donnees_reelles': etat_donnees_reelles(), 'change': True})
