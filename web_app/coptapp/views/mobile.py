"""Espace mobile : mot de passe temporaire d'un membre (sous-lot 2c)."""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.cache import add_never_cache_headers
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from compte.services.mobile import definir_mot_de_passe_membre
from compte.services.droits import membre_pour
from fenamo.htmx import veut_fragment


@require_POST
def definir_mot_de_passe_mobile(request, id):
    """Génère un mot de passe temporaire pour l'espace mobile du membre `id` (POST, jeton CSRF).

    404 hors périmètre, 403 sans droit d'enregistrer des membres (jamais en lecture seule). Le mot de passe n'est
    jamais mis dans les messages (stockés en session) ni dans une redirection : la réponse elle-même l'affiche UNE fois,
    dans le contexte dédié ``mot_de_passe`` (fragment ``partials/_mot_de_passe_mobile.html`` pour une requête HTMX, page
    complète sinon), avec ``Cache-Control: no-store``. Seul son hachage est enregistré et le journal ne le contient jamais.
    Les refus (membre supprimé, sans identifiant mobile) sont de simples messages suivis d'une redirection vers la fiche.
    """
    membre = membre_pour(request.user, id, 'peut_creer_membre')
    if membre.is_delete:
        messages.error(request, _("Ce membre est supprimé : aucun mot de passe ne peut être défini."))
        return redirect('membre-view', id=id)
    if not membre.idf:
        messages.error(request, _("Ce membre n'a pas d'identifiant mobile."))
        return redirect('membre-view', id=id)
    clair = definir_mot_de_passe_membre(request.user, membre)
    modele = ('coptapp/membres/partials/_mot_de_passe_mobile.html' if veut_fragment(request)
              else 'coptapp/membres/mot_de_passe_mobile.html')
    reponse = render(request, modele, {'membre': membre, 'mot_de_passe': clair})
    add_never_cache_headers(reponse)
    reponse['Cache-Control'] = 'no-store, private'
    return reponse
