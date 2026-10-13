"""Espace mobile : mot de passe temporaire d'un membre (sous-lot 2c)."""
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from compte.services.mobile import definir_mot_de_passe_membre
from coptapp.services.droits_provisoires import membre_pour


@require_POST
def definir_mot_de_passe_mobile(request, id):
    """Génère un mot de passe temporaire pour l'espace mobile du membre `id` (POST, jeton CSRF).

    404 hors périmètre, 403 sans droit d'enregistrer des membres (jamais en lecture seule). Le mot de passe n'est
    affiché QU'UNE fois, dans le message qui suit la redirection ; seul son hachage est enregistré et le journal ne le
    contient jamais. Un membre sans identifiant mobile (``idf``) n'a pas d'espace mobile : message d'erreur.
    """
    membre = membre_pour(request.user, id, 'peut_creer_membre')
    if not membre.idf:
        messages.error(request, _("Ce membre n'a pas d'identifiant mobile."))
        return redirect('membre-view', id=id)
    clair = definir_mot_de_passe_membre(request.user, membre)
    messages.success(request, _("Mot de passe temporaire de l'espace mobile : %(mdp)s (identifiant %(idf)s). "
                                "Il ne sera plus affiché : communiquez-le au membre.") % {'mdp': clair, 'idf': membre.idf})
    return redirect('membre-view', id=id)
