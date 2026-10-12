from django.contrib.auth.decorators import login_not_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST
from coptapp.models import Membre
from compte.forms import AddUserForm, ChangementMotDePasseForm
from compte.permissions import superuser_requis
from compte.services.verrou import ip_bloquee
from compte.services.comptes import changer_mot_de_passe, creer_compte, creer_compte_pour_membre

@superuser_requis
@require_POST
@never_cache
def adminer(request, id):
    """Crée le compte d'un membre. Le mot de passe temporaire est dans la réponse au POST (jamais en
    message flash ni en cache) : il n'est affiché qu'une fois."""
    membre = get_object_or_404(Membre, id=id)
    compte, mdp = creer_compte_pour_membre(membre, auteur=request.user)
    if not mdp:
        messages.info(request, _("Ce membre a déjà un compte (%(pseudo)s).") % {'pseudo': compte.username})
        return redirect('membre-view', id=id)
    modele = 'compte/partials/_compte_cree.html' if request.htmx else 'compte/compte_cree.html'
    return render(request, modele, {'compte': compte, 'mot_de_passe': mdp, 'membre': membre})

@login_not_required
@sensitive_post_parameters('password')
def connexion(request):
    if request.user.is_authenticated:
        return redirect('tableau-bord')
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        if ip_bloquee(request):
            return render(request, 'compte/verrou.html', status=429)
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('tableau-bord')
        elif user is None:
            classMessage = 'alert alert-danger'
            message = _("Pseudo ou mot de passe incorrect !")
    return render(request, 'compte/pages-login.html', locals())

@require_POST
def deconnexion(request):
    logout(request)
    return redirect('application')


# Comptes

@superuser_requis
@never_cache
def add_user(request):
    if request.method == 'POST':
        form = AddUserForm(request.POST)
        if form.is_valid():
            compte, mdp = creer_compte(
                form.cleaned_data['username'], form.cleaned_data['email'], auteur=request.user,
            )
            message = _("Compte créé. Pseudo : %(pseudo)s - mot de passe temporaire : %(mdp)s "
                        "(affiché une seule fois ; à changer à la première connexion).") % {
                'pseudo': compte.username, 'mdp': mdp}
            classe = 'alert alert-success text-center'
            form = AddUserForm()
    else:
        form = AddUserForm()
    return render(request, 'app/add-user.html', locals())


@sensitive_post_parameters('old_password', 'new_password1', 'new_password2')
def securite(request):
    """Changement de son propre mot de passe : ancien mot de passe exigé, nouveau validé."""
    force_changement = request.user.doit_changer_mot_de_passe
    form = ChangementMotDePasseForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        changer_mot_de_passe(request.user, form)
        update_session_auth_hash(request, request.user)
        messages.success(request, _("Mot de passe modifié."))
        return redirect('tableau-bord')
    return render(request, 'compte/securite.html', {'form': form, 'force': force_changement})
