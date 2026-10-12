from django.contrib.auth.decorators import login_not_required
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from coptapp.models import Membre
from compte.forms import *
from compte.permissions import superuser_requis
from compte.services.comptes import creer_compte, creer_compte_pour_membre

User = get_user_model()

# Create your views here.

@superuser_requis
@require_POST
def adminer(request, id):
    """Crée le compte d'un membre : mot de passe aléatoire affiché une seule fois."""
    membre = get_object_or_404(Membre, id=id)
    compte, mdp = creer_compte_pour_membre(membre, auteur=request.user)
    if mdp:
        messages.success(
            request,
            f"Compte créé. Pseudo : {compte.username} - mot de passe temporaire : {mdp} "
            "(à transmettre au membre ; il devra le changer à sa première connexion, il ne sera plus affiché).",
        )
    else:
        messages.info(request, f"Ce membre a déjà un compte ({compte.username}).")
    return redirect('membre-view', id=id)

@login_not_required
def connexion(request):
    if request.user.is_authenticated:
        return redirect('tableau-bord')
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('tableau-bord')
        elif user is None:
            classMessage = 'alert alert-danger'
            message = "Pseudo ou mot de passe incorrect !"
    return render(request, 'compte/pages-login.html', locals())

@require_POST
def deconnexion(request):
    logout(request)
    return redirect('application')


# Comptes

@superuser_requis
def add_user(request):
    if request.method == 'POST':
        form = AddUserForm(request.POST)
        if form.is_valid():
            compte, mdp = creer_compte(
                form.cleaned_data['username'], form.cleaned_data['email'], auteur=request.user,
            )
            message = (f"Compte créé. Pseudo : {compte.username} - mot de passe temporaire : {mdp} "
                       "(affiché une seule fois ; à changer à la première connexion).")
            classe = 'alert alert-success text-center'
            form = AddUserForm()
    else:
        form = AddUserForm()
    return render(request, 'app/add-user.html', locals())


def securite(request, id=None):
    """Changement de son propre mot de passe : ancien mot de passe exigé, nouveau validé."""
    force_changement = request.user.doit_changer_mot_de_passe
    form = ChangementMotDePasseForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        request.user.doit_changer_mot_de_passe = False
        request.user.save(update_fields=['doit_changer_mot_de_passe'])
        update_session_auth_hash(request, request.user)
        messages.success(request, "Mot de passe modifié.")
        return redirect('tableau-bord')
    return render(request, 'compte/securite.html', {'form': form, 'force': force_changement})
