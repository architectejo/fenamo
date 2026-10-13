"""Service contrôlé des pièces et photos privées (cahier des charges web § 9.1 et § 9.4).

Aucun de ces fichiers n'est servi sous ``/media/`` : ils vivent sous ``PRIVATE_MEDIA_ROOT`` et ne sortent que par ces vues,
qui exigent la connexion (middleware), le droit et le périmètre, fixent le ``Content-Type`` d'après le contenu réel,
ajoutent ``X-Content-Type-Options: nosniff`` et un ``Content-Disposition`` au nom neutre, et journalisent la
consultation d'une PIÈCE (pas d'une photo, consultée en continu dans les listes).

Droits :
- photo d'un membre : membre dans le périmètre du compte (``membre_pour``) ;
- pièce d'un membre (``fiche_id``) et pièces d'une association membre (``capture_justice``, ``preuve_de_paiement``) :
  idem plus le droit d'enregistrer des membres (``peut_creer_membre`` : jamais en lecture seule) ; association dans
  celles du compte (``associations_du_compte``).
"""
from urllib.parse import unquote

from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from compte.models import JournalAction
from compte.services.journal import journaliser
from coptapp.models import AssociationMembre, Membre
from coptapp.services.droits_provisoires import associations_du_compte, droits_membre, membre_pour
from coptapp.validators import mime_reel, nom_vignette

CHAMPS = {
    'membre': {'photo': False, 'fiche_id': True},  # champ -> est une pièce (journalisée, droit renforcé)
    'association': {'capture_justice': True, 'preuve_de_paiement': True},
}
EXTENSIONS = {'application/pdf': 'pdf', 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}


def _reponse(request, objet, champ, piece, vignette):
    fichier = getattr(objet, champ)
    if not fichier:
        raise Http404
    nom = fichier.name
    if vignette and not piece:
        candidate = nom_vignette(nom)
        if fichier.storage.exists(candidate):
            nom = candidate
    if not fichier.storage.exists(nom):
        raise Http404
    mime = mime_reel(fichier.storage.path(nom))
    if mime is None:
        raise Http404  # contenu non reconnu : jamais servi
    if piece:
        journaliser(request.user, JournalAction.Action.CONSULTATION_PIECE, objet, libelle=champ)
    reponse = FileResponse(fichier.storage.open(nom, 'rb'), content_type=mime)
    reponse['Content-Disposition'] = f'inline; filename="{champ}.{EXTENSIONS[mime]}"'  # nom neutre : jamais celui de l'envoi
    reponse['X-Content-Type-Options'] = 'nosniff'
    reponse['Cache-Control'] = 'private, no-store' if piece else 'private, max-age=600'
    return reponse


def servir(request, type_objet, id, champ, vignette=False):
    """404 hors périmètre ou pour un type/champ inconnu ; 403 sans droit sur une pièce."""
    if champ not in CHAMPS.get(type_objet, {}):
        raise Http404
    piece = CHAMPS[type_objet][champ]
    user = request.user
    if type_objet == 'membre':
        objet = membre_pour(user, id)
        if piece and not droits_membre(user, objet)['peut_creer_membre']:
            raise PermissionDenied
    else:
        objet = get_object_or_404(associations_du_compte(user), id=id)
        if not droits_membre(user)['peut_creer_membre']:
            raise PermissionDenied
    return _reponse(request, objet, champ, piece, vignette)


@require_GET
def fichier_prive(request, type_objet, id, champ):
    """/fichiers/<type>/<id>/<champ>/ ; ``?vignette=1`` : vignette 160 px d'une photo."""
    return servir(request, type_objet, id, champ, vignette=request.GET.get('vignette') == '1')


@require_GET
def fichier_par_nom(request, nom):
    """/fichiers/nom/<nom stocké> : adresse renvoyée par ``champ.url`` (gabarits hérités) ; mêmes contrôles que ci-dessus."""
    nom = unquote(nom).lstrip('./')
    candidats = [(False, nom)]
    if '_vignette.' in nom:
        candidats.append((True, nom.replace('_vignette.', '.')))
    for vignette, candidat in candidats:
        for modele, type_objet in ((Membre, 'membre'), (AssociationMembre, 'association')):
            for champ in CHAMPS[type_objet]:
                trouve = modele.objects.filter(**{champ: candidat}).first()
                if trouve is not None:
                    return servir(request, type_objet, trouve.pk, champ, vignette=vignette)
    raise Http404
