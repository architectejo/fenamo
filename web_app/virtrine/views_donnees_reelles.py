"""Interrupteur « données réelles » du site public : super-utilisateur seul, POST + CSRF (modale de confirmation)."""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from compte.permissions import superuser_requis
from fenamo.htmx import reponse_succes
from virtrine.models import Config
from virtrine.services import contenu

EVENEMENT = 'donneesReellesModifiees'
MOTIF_MAX = 500


@require_http_methods(['GET', 'POST'])
@superuser_requis
def donnees_reelles(request):
    """GET : modale de confirmation. POST ``actif`` (1 pour afficher les données réelles, 0 pour le jeu d'exemple) et ``motif`` facultatif.

    Contexte de la modale : action, actif (état actuel), cible (état demandé), motif_max, erreur. HTMX : 204 + toast + événement
    ``donneesReellesModifiees`` ; sinon message et retour à l'écran du contenu du site."""
    actuel = Config.instance().donnees_reelles_actif
    contexte = {'action': request.path, 'actif': actuel, 'cible': not actuel, 'motif_max': MOTIF_MAX}
    if request.method == 'GET':
        return render(request, 'virtrine/partials/_modale_donnees_reelles.html', contexte)
    voulu = (request.POST.get('actif') or '').strip().lower() in ('1', 'true', 'on', 'oui')
    try:
        contenu.definir_donnees_reelles(request.user, voulu, request.POST.get('motif', ''))
    except ValidationError as erreur:
        return render(request, 'virtrine/partials/_modale_donnees_reelles.html', {**contexte, 'erreur': ' '.join(erreur.messages)}, status=422)
    message = _("Le site affiche maintenant les données réelles.") if voulu else _("Le site affiche maintenant son jeu d'exemple.")
    if request.htmx:
        return reponse_succes(message, evenements=[EVENEMENT])
    messages.success(request, message)
    return redirect('site')
