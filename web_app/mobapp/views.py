from django.shortcuts import redirect, render
from coptapp.models import Membre, Moto
from mobapp.forms import *
from datetime import date
# Create your views here.

today = date.today()

def home(request):
    title = "Authentification"
    if request.method == 'POST':
        idf_post = request.POST.get('idf')
        password = request.POST.get('pass')

        membre = Membre.objects.filter(idf=idf_post).first()
        if membre == None:
            message = "Identifiant non reconnu !"
            classe = "alert alert-danger"
        else:
            if request.POST.get('pass') == '' and not membre.password: return redirect('session', id=membre.id)
            if membre.password == password:
                return redirect('session', id=membre.id)
            else:
                message = "Mot de passe incorrect !"
                classe = "alert alert-danger"
    return render(request, 'mob/home.html', locals())

def register(request):
    title = "Enregistrement"
    if request.method == 'POST':
        form = MembreFormRegister(request.POST, request.FILES)
        if form.is_valid():
            membre = form.save(commit=False)
            membre.save()
            idf = 'MBR'+str(membre.id).zfill(7)
            membre.idf = idf
            membre.save()
            return redirect('data', id=membre.id)
        else:
            message = "Echec d'enregistrement !"
            classe = 'alert alert-danger text-center'
    else:
        form = MembreFormRegister()
    return render(request, 'mob/register.html', locals())

def session(request, id):
    try:
        membre = Membre.objects.get(id=id)
        motos = Moto.objects.filter(proprietaire=membre)
        if request.method == 'POST':
            form = MotoFormRegister(request.POST, request.FILES)
            if form.is_valid():
                moto = form.save(commit=False)
                dernier = Moto.objects.filter(province=membre.province).last()
                if dernier == None:
                    numero = 1
                else:
                    numero = dernier.numero.replace(membre.province.sigle,'')
                    numero = int(numero)+1
                if numero < 100:
                    numero = str(numero).zfill(3)+str(membre.province.sigle)
                else:
                    numero = str(numero)+str(membre.province.sigle)
                moto.proprietaire = membre
                moto.numero = numero
                moto.abonnement = today.replace(day=1, year=int(today.year)+1)
                moto.province = membre.province
                moto.ville = membre.ville
                moto.structure = membre.structure
                verify = Moto.objects.filter(proprietaire=membre,num_chassie=moto.num_chassie, num_moteur=moto.num_moteur).last()
                if verify == None:
                    moto.save()
                    message = "Mise à jour !"
                    classe = 'alert alert-success text-center'
                else:
                    message = "La moto est déjà enregistré !"
                    classe = 'alert alert-danger text-center'
            else:
                message = "La moto est déjà enregistré !"
                classe = 'alert alert-danger text-center'
        else:
            form = MotoFormRegister()
    except Exception as error:
        print(f"\n\n\n{error}\n\n\n")
    return render(request, 'mob/session.html', locals())

def data_membre(request, id):
    try:
        membre = Membre.objects.get(id=id)
        structures = Structure.objects.filter(province=membre.province).exclude(ville=None)
        villes = Ville.objects.filter(province=membre.province).exclude(nom=None)
        if membre.ville:
            return redirect('session', id=membre.id)
        if request.method == 'POST':
            if request.POST.get('structure'):
                structure = Structure.objects.get(id=int(request.POST.get('structure')))
                membre.structure = structure
                membre.ville = structure.ville
            if request.POST.get('ville'):
                ville = Ville.objects.get(id=int(request.POST.get('ville')))
                membre.ville = ville
            membre.save()
            return redirect('session', id=membre.id)
    except Exception as error:
        pass
    return render(request, 'mob/data.html', locals())

def attribut_ville(request, id, id_ville):
    try:
        ville = Ville.objects.get(id=id_ville)
        membre = Membre.objects.get(id=id)
        membre.ville = ville
        membre.save()
    except:
        pass
    return redirect('data', id=id)

def attribut_str(request, id, id_str):
    try:
        structure = Structure.objects.get(id=id_str)
        membre = Membre.objects.get(id=id)
        membre.structure = structure
        membre.save()
    except:
        pass
    return redirect('data', id=id)