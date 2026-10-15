"""Verrouillage de l'application (F-07) : écran et modales, super-utilisateur seul (``superuser_requis``), POST + CSRF."""
from datetime import timedelta

from django.contrib import messages
from django.contrib.sessions.models import Session
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from django.contrib.auth import get_user_model

from compte.models import JournalAction
from compte.permissions import superuser_requis
from compte.services import verrou_application as verrou
from fenamo.htmx import reponse_succes, veut_fragment

EVENEMENT = 'verrouModifie'


ACTIONS_VERROU = (JournalAction.Action.VERROUILLAGE_APPLICATION, JournalAction.Action.DEVERROUILLAGE_APPLICATION)


def duree_en_texte(ecart):
    """« 2 h 15 », « 35 min », « 3 j 4 h » (espaces insécables) à partir d'un timedelta."""
    minutes = max(int(ecart.total_seconds() // 60), 0)
    jours, reste = divmod(minutes, 1440)
    heures, minutes = divmod(reste, 60)
    if jours:
        return f"{jours} j {heures} h"
    if heures:
        return f"{heures} h {minutes:02d}"
    return f"{minutes} min"


def sessions_ouvertes():
    """(total, hors super-utilisateurs) des sessions non expirées : le nombre réel annoncé avant de verrouiller."""
    ids_su = {str(pk) for pk in get_user_model().objects.filter(is_superuser=True).values_list('pk', flat=True)}
    total = hors_su = 0
    for session in Session.objects.filter(expire_date__gt=timezone.now()).only('session_data')[:5000]:
        try:
            auteur = str(session.get_decoded().get('_auth_user_id', ''))
        except Exception:  # session illisible (clé changée) : comptée comme anonyme, jamais bloquante
            auteur = ''
        if not auteur:
            continue
        total += 1
        if auteur not in ids_su:
            hors_su += 1
    return total, hors_su


def historique_verrou(limite=5):
    """Derniers changements d'état (journal), du plus récent au plus ancien ; durée d'un verrouillage rapportée à son déverrouillage."""
    lignes = list(JournalAction.objects.filter(action__in=ACTIONS_VERROU).select_related('auteur').defer('avant', 'apres')
                  .order_by('-date', '-id')[:limite + 1])
    entrees = []
    for i, ligne in enumerate(lignes[:limite]):
        verrouillage = ligne.action == JournalAction.Action.VERROUILLAGE_APPLICATION
        precedent = next((x for x in lignes[i + 1:] if x.action == JournalAction.Action.VERROUILLAGE_APPLICATION), None)
        entrees.append({'verrouillage': verrouillage, 'date': ligne.date, 'auteur': ligne.auteur.get_username() if ligne.auteur else '',
                        'motif': ligne.motif, 'duree': duree_en_texte(ligne.date - precedent.date) if (not verrouillage and precedent) else ''})
    return entrees


def contexte_etat(etat):
    courant = {'etat': etat, 'historique': historique_verrou()}
    courant['sessions_total'], courant['sessions_hors_su'] = sessions_ouvertes()
    if etat.verrouillee and etat.depuis:
        courant['duree'] = duree_en_texte(timezone.now() - etat.depuis)
    dernier = next((e for e in courant['historique'] if not e['verrouillage'] and e['duree']), None)
    courant['derniere_periode'] = dernier
    return courant


@require_GET
@superuser_requis
@never_cache
def verrou_application(request):
    """Écran de l'état : verrouillée ou non, message, depuis quand, par qui (visible du seul super-utilisateur). Fragment HTMX : la zone d'état
    seule, avec la classe « change » (animation « tampon ») : elle n'est demandée qu'après un changement d'état."""
    contexte = contexte_etat(verrou.etat())
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
    total, hors_su = sessions_ouvertes()
    contexte = {'action': request.path, 'message_max': verrou.MESSAGE_MAX, 'motif_max': verrou.MOTIF_MAX, 'etat': etat_courant, 'sessions_hors_su': hors_su}
    if request.method == 'GET':
        return render(request, 'compte/partials/_modale_verrouiller.html', contexte)
    message, motif = (request.POST.get('message') or '').strip(), (request.POST.get('motif') or '').strip()
    try:
        verrou.verrouiller(request.user, message, motif)
    except verrou.RegleVerrou as erreur:
        return render(request, 'compte/partials/_modale_verrouiller.html', {**contexte, 'erreur_message': str(erreur), 'valeur_message': message,
                                                                           'valeur_motif': motif}, status=422)
    return _terminer(request, _("Application verrouillée"))


@require_http_methods(['GET', 'POST'])
@superuser_requis
def deverrouiller(request):
    etat_courant = verrou.etat()
    contexte = {'action': request.path, 'motif_max': verrou.MOTIF_MAX, 'etat': etat_courant,
                'duree': duree_en_texte(timezone.now() - etat_courant.depuis) if etat_courant.depuis else ''}
    if request.method == 'GET':
        return render(request, 'compte/partials/_modale_deverrouiller.html', contexte)
    try:
        verrou.deverrouiller(request.user, (request.POST.get('motif') or '').strip())
    except verrou.RegleVerrou as erreur:
        return render(request, 'compte/partials/_modale_deverrouiller.html', {**contexte, 'erreur': str(erreur)}, status=422)
    return _terminer(request, _("Application déverrouillée"))
