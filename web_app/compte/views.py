from django.contrib.auth.decorators import login_not_required
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.shortcuts import redirect, render
from coptapp.models import Membre
from compte.forms import *

User = get_user_model()

# Create your views here.

def adminer(request, id):
    membre = Membre.objects.get(id=id)
    tabname = membre.nom.split(' ')
    username = f'{tabname[0]}{id}'
    email = f'{username}@fenamo.cd'.lower()
    verify = User.objects.filter(membreId=id)
    if len(verify) == 0:
        creation = User.objects.create_user(username=email, password=email, email=email, membreId=id)
        membre.is_user = True
        membre.save()
        membre.structure.users.add(creation)
        membre.structure.save()
    return redirect('membre-view', id=id)

@login_not_required
def connexion(request):
    if request.user.is_authenticated:
        return redirect('tableau-bord')
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('tableau-bord')
        elif user is None:
            classMessage = 'alert alert-danger'
            message = "Pseudo ou mot de passe incorrect !"
    return render(request, 'compte/pages-login.html', locals())

def deconnexion(request):
    logout(request)
    return redirect('application')


# Utilisateurs d une association membre

def add_user(request):
    if request.method == 'POST':
        form = AddUserForm(request.POST)
        if form.is_valid():
            Compte.objects.create_user(**form.cleaned_data,privilege5=True)
            message = "Ajout d'un nouveau utilisateur !"
            classe = 'alert alert-success text-center'
    else:
        form = AddUserForm()
    return render(request, 'app/add-user.html', locals())

def delete_user(request):
    if request.method == 'POST':
        if request.user:
            deleter = Compte.objects.get(id=request.user.id)
            deleter.delete()
        return redirect('deconnexion')
    return render(request, 'app/delete-user.html', locals())