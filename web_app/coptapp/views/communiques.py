"""Communiqués (F-40) : liste et lecture (GET), publication (modale, POST + CSRF), marquage « lu » (POST), compteur du badge (fragment HTMX).

Vues minces : les règles sont dans ``coptapp.services.communiques``. La lecture ne modifie rien (le « lu » est un POST distinct)."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.cache import add_never_cache_headers
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from coptapp.models import Antenne, Province
from coptapp.services import communiques as service
from fenamo.htmx import reponse_succes, veut_fragment

EVENEMENT = 'communiquesMaj'


def _entier(valeur):
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        return None
    return nombre if 0 < nombre <= 2**31 - 1 else None


def _modele(request):
    """La modale pour HTMX, la page de repli (même fragment dans la coque) sinon."""
    return 'coptapp/communiques/partials/_modale_publier.html' if veut_fragment(request) else 'coptapp/communiques/publier.html'


@require_GET
def listMessage(request):
    """Liste des communiqués visibles. GET : ``q``, ``etat`` (non_lus), ``coordination``, ``antenne``, ``page``. Contexte : page_obj,
    communiques (= page_obj, compatibilité), filtres, filtres_actifs, nb_non_lus, peut_publier, choix (``coordinations`` et ``antennes``
    de ``service.choix_ciblage``, pour les listes de filtre), nombres (``tous`` et ``non_lus`` des puces, selon q, coordination, antenne ;
    ``nb_non_lus`` = tout le périmètre). Chaque communiqué de la page porte ``lu`` et ``titre_affiche``. Fragment HTMX : la zone seule."""
    filtres = {cle: (request.GET.get(cle) or '').strip() for cle in ('q', 'etat', 'coordination', 'antenne')}
    page = service.lister_communiques(request.user, filtres, request.GET.get('page'))
    contexte = {'page_obj': page, 'communiques': page, 'filtres': filtres, 'filtres_actifs': any(filtres.values()),
                'nb_non_lus': service.nombre_non_lus(request.user), 'peut_publier': service.peut_publier(request.user),
                'choix': service.choix_ciblage(), 'nombres': service.nombres_liste(request.user, filtres)}
    modele = 'coptapp/communiques/partials/_liste.html' if veut_fragment(request) else 'app/list-message.html'
    return render(request, modele, contexte)


@require_GET
def messageView(request, id):
    """Lecture d'un communiqué visible (404 sinon). N'écrit rien. Contexte : message (= communique), lu, peut_publier, titre_affiche, suivant (prochain non lu ou None)."""
    communique = get_object_or_404(service.communiques_visibles(request.user).select_related('user', 'province', 'antenne'), id=id)
    lu = service.est_lu(request.user, communique)
    return render(request, 'app/message-view.html', {
        'message': communique, 'communique': communique, 'lu': lu,
        'titre_affiche': service.titre_affiche(communique), 'suivant': service.suivant_non_lu(request.user, apres=communique),
        'peut_publier': service.peut_publier(request.user)})


@require_POST
def lu(request, id):
    """Marque le communiqué lu POUR le compte connecté (404 s'il n'est pas visible). HTMX : 204 + événement ``communiquesMaj`` ;
    sinon retour à la lecture."""
    communique = get_object_or_404(service.communiques_visibles(request.user), id=id)
    service.marquer_lu(request.user, communique)
    if request.htmx:
        return reponse_succes(None, evenements=[EVENEMENT])
    return redirect('communique', id=communique.pk)


@require_GET
def compteur(request):
    """Fragment du badge : nombre de communiqués non lus (contexte nb_non_lus), jamais mis en cache. À rafraîchir côté gabarit par
    ``hx-trigger="every 120s"``."""
    reponse = render(request, 'coptapp/communiques/partials/_compteur.html', {'nb_non_lus': service.nombre_non_lus(request.user)})
    add_never_cache_headers(reponse)
    return reponse


@require_http_methods(['GET', 'POST'])
def addCommunique(request):
    """Publication (ED, SU) dans la modale commune. 403 sans droit. POST : ``titre``, ``message``, ``cible`` (national, coordination, antenne ;
    absent = déduit des listes), ``coordination`` et ``antenne`` (identifiants ; le contexte porte ``coordinations`` et ``antennes``, voir ``service.choix_ciblage``). Erreur : 422 (modale conservée ; contexte ``erreur`` générale,
    ``erreurs`` = {champ: texte} pour les messages sous les champs, ``valeurs``) ; succès : HTMX 204 + toast + ``communiquesMaj``, sinon message et retour à la liste."""
    if not service.peut_publier(request.user):
        raise PermissionDenied
    contexte = {'action': request.path, **service.choix_ciblage(),
                'titre_max': service.TITRE_MAX, 'message_max': service.MESSAGE_MAX}
    if request.method == 'GET':
        return render(request, _modele(request), contexte)
    donnees = {cle: request.POST.get(cle, '') for cle in ('titre', 'message', 'cible', 'coordination', 'antenne')}
    coordination = Province.objects.filter(pk=_entier(donnees['coordination'])).first() if donnees['coordination'] else None
    antenne = Antenne.objects.filter(pk=_entier(donnees['antenne'])).first() if donnees['antenne'] else None
    try:
        if (donnees['coordination'] and coordination is None) or (donnees['antenne'] and antenne is None):
            raise service.ErreurCommunique(_("Ciblage inconnu."), 'antenne' if donnees['antenne'] else 'coordination')
        service.publier(request.user, donnees['titre'], donnees['message'], coordination, antenne,
                        cible=donnees['cible'].strip() or None)
    except service.ErreurCommunique as erreur:
        erreurs = {erreur.champ: str(erreur)} if erreur.champ else {}
        return render(request, _modele(request), {**contexte, 'erreur': str(erreur), 'erreurs': erreurs, 'valeurs': donnees}, status=422)
    texte = _("Communiqué publié.")
    if request.htmx:
        return reponse_succes(texte, evenements=[EVENEMENT])
    messages.success(request, texte)
    return redirect('list-message')
