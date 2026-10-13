"""Application mobile actuelle (/mob/), reprise au sous-lot 2c (cahier des charges web § 9.1 et § 2.3).

Compatibilité : les adresses /mob/… et les noms de routes ne changent pas. Sécurité :
- connexion par identifiant + mot de passe HACHÉ (``check_password``) ; un membre sans mot de passe ne peut pas se
  connecter tant qu'un agent n'en a pas défini (``manage.py definir_mot_de_passe_membre``) ; un seul message pour tout
  échec (identifiant inconnu, sans mot de passe, mauvais mot de passe) et un hachage factice si l'identifiant est inconnu ;
- limitation des tentatives par identifiant et par adresse IP (``compte.services.mobile``) ;
- après la connexion, la session porte ``mob_membre_id`` ET une empreinte HMAC du hachage du mot de passe : changer le mot de
  passe invalide la session ; ``POST /mob/deconnexion/`` la ferme ;
- l'espace, les données, les rattachements et la photo d'un membre exigent cette session (403 sinon) ;
- les rattachements (association membre, antenne) ne se font que par POST avec jeton CSRF ;
- toutes les pages personnelles sont envoyées avec ``Cache-Control: no-store``.
"""
from functools import wraps

from django.contrib.auth.hashers import make_password
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.cache import add_never_cache_headers
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from compte.services.mobile import (
    connexion_bloquee, effacer_echecs, empreinte_session, inscriptions_trop_nombreuses, noter_echec, noter_inscription,
    session_valide, verifier_mot_de_passe,
)
from coptapp.models import Antenne, AssociationMembre, Membre, Ville
from coptapp.services.engins import CoordinationInconnue, EnginDejaEnregistre, enregistrer_engin
from coptapp.services.fichiers_prives import reponse_fichier
from coptapp.services.geographie import rattacher_antenne, rattacher_association, rattacher_ville
from mobapp.forms import InscriptionMobileForm, MotoFormRegister

CLES_SESSION = ('mob_membre_id', 'mob_empreinte')
CHAMPS_ENGIN = ('num_plaque', 'num_moteur', 'num_chassie', 'marque', 'couleur')


def sans_cache(vue):
    """Page personnelle : jamais conservée par le navigateur ni un intermédiaire (``Cache-Control: no-store, private``)."""
    @wraps(vue)
    def enveloppe(request, *args, **kwargs):
        reponse = vue(request, *args, **kwargs)
        add_never_cache_headers(reponse)
        reponse['Cache-Control'] = 'no-store, private'
        return reponse
    return enveloppe


def ouvrir_session(request, membre):
    """Connecte `membre` à l'espace mobile (nouvelle clé de session : pas de fixation de session)."""
    request.session.cycle_key()
    request.session['mob_membre_id'] = membre.id
    request.session['mob_empreinte'] = empreinte_session(membre)


def membre_connecte(vue):
    """Réserve la vue au membre connecté dont l'identifiant est celui de l'adresse et dont le mot de passe n'a pas changé
    depuis la connexion : 403 sinon."""
    @wraps(vue)
    def enveloppe(request, id, *args, **kwargs):
        if not session_valide(request.session, id):
            raise PermissionDenied
        return vue(request, id, *args, **kwargs)
    return enveloppe


def _message(request, texte, niveau):
    """Contexte d'un message : ``niveau`` vaut 'succes' ou 'danger' (affiché par mob/_message.html)."""
    return {'message': texte, 'niveau': niveau}


@sans_cache
def home(request):
    title = _("Authentification")
    contexte = {'title': title}
    if request.method == 'POST':
        idf_post = (request.POST.get('idf') or '').strip()
        password = request.POST.get('pass') or ''
        if connexion_bloquee(request, idf_post):
            contexte.update(_message(request, _("Trop d'essais : réessayez plus tard."), 'danger'))
            return render(request, 'mob/home.html', contexte, status=429)
        membre = Membre.objects.filter(idf=idf_post, is_delete=False).first() if idf_post else None
        if verifier_mot_de_passe(membre, password):
            effacer_echecs(request, idf_post)
            ouvrir_session(request, membre)
            return redirect('session', id=membre.id)
        noter_echec(request, idf_post)  # message UNIQUE (rien ne révèle si l'identifiant existe) ; toutes les branches d'échec comptent, y compris « mot de passe à définir »
        contexte.update(_message(request, _("Identifiant ou mot de passe incorrect."), 'danger'))
    return render(request, 'mob/home.html', contexte)


@sans_cache
def register(request):
    contexte = {'title': _("Enregistrement")}
    if request.method == 'POST':
        form = InscriptionMobileForm(request.POST, request.FILES)
        if inscriptions_trop_nombreuses(request):
            contexte.update(_message(request, _("Trop d'inscriptions depuis cette connexion : réessayez plus tard."), 'danger'))
            return render(request, 'mob/register.html', {**contexte, 'form': form}, status=429)
        if form.is_valid():
            with transaction.atomic():
                membre = form.save(commit=False)
                membre.password = make_password(form.cleaned_data['password1'])
                membre.save()
                membre.idf = 'MBR' + str(membre.id).zfill(7)
                membre.save(update_fields=['idf'])
            noter_inscription(request)
            ouvrir_session(request, membre)
            return redirect('data', id=membre.id)
        contexte.update(_message(request, _("Échec de l'enregistrement !"), 'danger'))
    else:
        form = InscriptionMobileForm()
    return render(request, 'mob/register.html', {**contexte, 'form': form})


@require_POST
def deconnexion(request):
    """Ferme l'espace mobile : retire la session du membre (la session du site, si elle existe, n'est pas touchée)."""
    for cle in CLES_SESSION:
        request.session.pop(cle, None)
    request.session.cycle_key()
    return redirect('home-mob')


@sans_cache
@membre_connecte
def session(request, id):
    membre = get_object_or_404(Membre, id=id, is_delete=False)
    contexte = {'membre': membre}
    form = MotoFormRegister()
    if request.method == 'POST':
        form = MotoFormRegister(request.POST, request.FILES)
        if form.is_valid():
            donnees = {champ: form.cleaned_data[champ] for champ in CHAMPS_ENGIN}
            try:
                enregistrer_engin(membre, None, donnees, photo=form.cleaned_data.get('photo'))
            except CoordinationInconnue:
                contexte.update(_message(request, _("Votre coordination provinciale est inconnue : contactez votre agent."), 'danger'))
            except EnginDejaEnregistre:
                contexte.update(_message(request, _("Cet engin est déjà enregistré (même numéro de châssis et de moteur)."), 'danger'))
            else:
                contexte.update(_message(request, _("Engin enregistré."), 'succes'))
                form = MotoFormRegister()
        else:
            contexte.update(_message(request, _("Vérifiez les informations de l'engin."), 'danger'))
    contexte.update({'form': form, 'motos': membre.moto_set.all()})
    return render(request, 'mob/session.html', contexte)


def _deja_valide(membre):
    """Vrai si le dossier a passé une validation (is_validate2 ou is_validate3) : le membre ne change plus seul ses rattachements
    (``is_validate1`` vaut True dès la création, il ne signifie pas « validé »)."""
    return bool(membre.is_validate2 or membre.is_validate3)


def _choix_du_membre(membre):
    """Associations membres, antennes héritées (« villes ») et antennes proposées : celles de la coordination du membre.

    Une coordination récente peut n'avoir que des antennes (aucune ville héritée) : le membre doit pouvoir terminer l'étape
    « données » avec ce qui existe. Une association est proposée dès qu'elle a une ville OU une antenne.
    """
    if membre.province_id is None:  # coordination inconnue : rien à proposer (jamais « toutes les associations sans province »)
        return AssociationMembre.objects.none(), Ville.objects.none(), Antenne.objects.none()
    associations = (AssociationMembre.objects.filter(Q(province=membre.province) | Q(antenne__coordination=membre.province))
                    .exclude(ville=None, antenne=None).distinct())
    villes = Ville.objects.filter(province=membre.province).exclude(nom=None)
    antennes = Antenne.objects.filter(coordination=membre.province).exclude(nom=None)
    return associations, villes, antennes


@sans_cache
@membre_connecte
def data_membre(request, id):
    membre = get_object_or_404(Membre, id=id, is_delete=False)
    associations, villes, antennes = _choix_du_membre(membre)
    if membre.ville or membre.antenne or _deja_valide(membre):
        return redirect('session', id=membre.id)
    if request.method == 'POST':
        with transaction.atomic():  # association + ville + antenne : tout ou rien
            if request.POST.get('structure'):
                rattacher_association(None, membre, get_object_or_404(associations, id=_entier(request.POST['structure'])))
            if request.POST.get('ville'):
                rattacher_ville(None, membre, get_object_or_404(villes, id=_entier(request.POST['ville'])))
            if request.POST.get('antenne'):
                rattacher_antenne(None, membre, get_object_or_404(antennes, id=_entier(request.POST['antenne'])))
        return redirect('session', id=membre.id)
    return render(request, 'mob/data.html', {'membre': membre, 'associations': associations, 'villes': villes,
                                             'antennes': antennes})


def _entier(texte):
    """Entier tiré d'un champ de formulaire ; 0 (introuvable, donc 404) si le texte n'en est pas un."""
    try:
        return int(texte)
    except (TypeError, ValueError):
        return 0


@require_POST
@sans_cache
@membre_connecte
def attribut_ville(request, id, id_ville):
    """POST seulement (jeton CSRF) : rattache le membre connecté à une antenne de sa coordination."""
    membre = get_object_or_404(Membre, id=id, is_delete=False)
    if membre.ville_id or membre.antenne_id or _deja_valide(membre):
        raise PermissionDenied  # déjà rattaché, ou dossier déjà validé : seul un agent le change
    rattacher_ville(None, membre, get_object_or_404(_choix_du_membre(membre)[1], id=id_ville))
    return redirect('data', id=id)


@require_POST
@sans_cache
@membre_connecte
def attribut_str(request, id, id_str):
    """POST seulement (jeton CSRF) : rattache le membre connecté à une association membre de sa coordination."""
    membre = get_object_or_404(Membre, id=id, is_delete=False)
    if membre.structure_id or _deja_valide(membre):
        raise PermissionDenied  # déjà rattaché à une association, ou dossier déjà validé : seul un agent le change
    rattacher_association(None, membre, get_object_or_404(_choix_du_membre(membre)[0], id=id_str))  # + ville et antenne cohérentes
    return redirect('data', id=id)


@require_GET
@sans_cache
@membre_connecte
def photo_membre(request, id):
    """Photo (ou vignette avec ``?vignette=1``) du membre connecté : l'espace mobile n'a pas de compte Django, il ne peut donc
    pas utiliser la vue /fichiers/… ; mêmes protections (type réel, nosniff, Content-Disposition neutre, no-store)."""
    membre = get_object_or_404(Membre, id=id, is_delete=False)
    return reponse_fichier(None, membre, 'photo', piece=False, vignette=request.GET.get('vignette') == '1')
