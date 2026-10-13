"""Application mobile actuelle (/mob/), reprise au sous-lot 2c (cahier des charges web § 9.1 et § 2.3).

Compatibilité : les adresses /mob/… et les noms de routes ne changent pas. Nouveautés de sécurité :
- connexion par identifiant + mot de passe HACHÉ (``check_password``) ; un membre sans mot de passe ne peut pas se
  connecter tant qu'un agent n'en a pas défini (``manage.py definir_mot_de_passe_membre``) ;
- limitation des tentatives par identifiant et par adresse IP (``compte.services.mobile``) ;
- après la connexion, ``request.session['mob_membre_id']`` ; l'espace, les données et les rattachements d'un membre exigent
  que cet identifiant soit celui de l'adresse (403 sinon) ;
- les rattachements (association membre, antenne) ne se font plus que par POST avec jeton CSRF.
"""
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from compte.services.mobile import (
    connexion_bloquee, effacer_echecs, inscriptions_trop_nombreuses, noter_echec, noter_inscription,
)
from coptapp.models import AssociationMembre, Membre, Ville
from coptapp.services.engins import CoordinationInconnue, EnginDejaEnregistre, enregistrer_engin
from mobapp.forms import InscriptionMobileForm, MotoFormRegister

SESSION_CLE = 'mob_membre_id'
CHAMPS_ENGIN = ('num_plaque', 'num_moteur', 'num_chassie', 'marque', 'couleur')


def ouvrir_session(request, membre):
    """Connecte `membre` à l'espace mobile (nouvelle clé de session : pas de fixation de session)."""
    request.session.cycle_key()
    request.session[SESSION_CLE] = membre.id


def membre_connecte(vue):
    """Réserve la vue au membre connecté dont l'identifiant est celui de l'adresse : 403 sinon."""
    def enveloppe(request, id, *args, **kwargs):
        if request.session.get(SESSION_CLE) != id:
            raise PermissionDenied
        return vue(request, id, *args, **kwargs)
    enveloppe.__name__ = vue.__name__
    enveloppe.__doc__ = vue.__doc__
    return enveloppe


def home(request):
    title = "Authentification"
    if request.method == 'POST':
        idf_post = (request.POST.get('idf') or '').strip()
        password = request.POST.get('pass') or ''
        if connexion_bloquee(request, idf_post):
            message = "Trop d'essais : réessayez plus tard."
            classe = "alert alert-danger"
            return render(request, 'mob/home.html', locals(), status=429)
        membre = Membre.objects.filter(idf=idf_post, is_delete=False).first() if idf_post else None
        if membre is None:
            noter_echec(request, idf_post)
            message = "Identifiant non reconnu !"
            classe = "alert alert-danger"
        elif not membre.password:
            message = "Mot de passe à définir : contactez votre agent."
            classe = "alert alert-danger"
        elif check_password(password, membre.password):
            effacer_echecs(request, idf_post)
            ouvrir_session(request, membre)
            return redirect('session', id=membre.id)
        else:
            noter_echec(request, idf_post)
            message = "Mot de passe incorrect !"
            classe = "alert alert-danger"
    return render(request, 'mob/home.html', locals())


def register(request):
    title = "Enregistrement"
    if request.method == 'POST':
        form = InscriptionMobileForm(request.POST, request.FILES)
        if inscriptions_trop_nombreuses(request):
            message = "Trop d'inscriptions depuis cette connexion : réessayez plus tard."
            classe = 'alert alert-danger text-center'
            return render(request, 'mob/register.html', locals(), status=429)
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
        message = "Echec d'enregistrement !"
        classe = 'alert alert-danger text-center'
    else:
        form = InscriptionMobileForm()
    return render(request, 'mob/register.html', locals())


@membre_connecte
def session(request, id):
    membre = get_object_or_404(Membre, id=id, is_delete=False)
    motos = membre.moto_set.all()
    if request.method == 'POST':
        form = MotoFormRegister(request.POST, request.FILES)
        if form.is_valid():
            donnees = {champ: form.cleaned_data[champ] for champ in CHAMPS_ENGIN}
            try:
                enregistrer_engin(membre, None, donnees, photo=form.cleaned_data.get('photo'))
            except CoordinationInconnue:
                message = "Votre coordination provinciale est inconnue : contactez votre agent."
                classe = 'alert alert-danger text-center'
            except EnginDejaEnregistre:
                message = "La moto est déjà enregistré !"
                classe = 'alert alert-danger text-center'
            else:
                message = "Mise à jour !"
                classe = 'alert alert-success text-center'
                form = MotoFormRegister()
        else:
            message = "Vérifiez les informations de la moto."
            classe = 'alert alert-danger text-center'
    else:
        form = MotoFormRegister()
    motos = membre.moto_set.all()
    return render(request, 'mob/session.html', locals())


def _choix_du_membre(membre):
    """Associations membres et antennes proposées : celles de la coordination du membre."""
    structures = AssociationMembre.objects.filter(province=membre.province).exclude(ville=None)
    villes = Ville.objects.filter(province=membre.province).exclude(nom=None)
    return structures, villes


@membre_connecte
def data_membre(request, id):
    membre = get_object_or_404(Membre, id=id, is_delete=False)
    structures, villes = _choix_du_membre(membre)
    if membre.ville:
        return redirect('session', id=membre.id)
    if request.method == 'POST':
        champs = []
        structure_id, ville_id = request.POST.get('structure'), request.POST.get('ville')
        if structure_id:
            structure = get_object_or_404(structures, id=int(structure_id)) if structure_id.isdigit() else None
            if structure is None:
                raise Http404
            membre.structure, membre.ville = structure, structure.ville
            champs += ['structure', 'ville']
        if ville_id:
            ville = get_object_or_404(villes, id=int(ville_id)) if ville_id.isdigit() else None
            if ville is None:
                raise Http404
            membre.ville = ville
            champs.append('ville')
        if champs:
            membre.save(update_fields=sorted(set(champs)) + ['mise_a_jour'])
        return redirect('session', id=membre.id)
    return render(request, 'mob/data.html', locals())


@require_POST
@membre_connecte
def attribut_ville(request, id, id_ville):
    """POST seulement (jeton CSRF) : rattache le membre connecté à une antenne de sa coordination."""
    membre = get_object_or_404(Membre, id=id, is_delete=False)
    ville = get_object_or_404(_choix_du_membre(membre)[1], id=id_ville)
    membre.ville = ville
    membre.save(update_fields=['ville', 'mise_a_jour'])
    return redirect('data', id=id)


@require_POST
@membre_connecte
def attribut_str(request, id, id_str):
    """POST seulement (jeton CSRF) : rattache le membre connecté à une association membre de sa coordination."""
    membre = get_object_or_404(Membre, id=id, is_delete=False)
    structure = get_object_or_404(_choix_du_membre(membre)[0], id=id_str)
    membre.structure = structure
    membre.save(update_fields=['structure', 'mise_a_jour'])
    return redirect('data', id=id)


@require_GET
@membre_connecte
def photo_membre(request, id):
    """Photo (ou vignette avec ``?vignette=1``) du membre connecté : l'espace mobile n'a pas de compte Django, il ne peut
    donc pas utiliser la vue /fichiers/… ; mêmes protections (type réel, nosniff, Content-Disposition neutre)."""
    from coptapp.views.fichiers import _reponse
    membre = get_object_or_404(Membre, id=id, is_delete=False)
    return _reponse(request, membre, 'photo', piece=False, vignette=request.GET.get('vignette') == '1')
