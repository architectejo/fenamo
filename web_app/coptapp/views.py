from django.shortcuts import redirect, render
from coptapp.models import *
from django.contrib.auth import authenticate, get_user_model, logout
from virtrine.models import Article, Contact, Galery
from coptapp.forms import *
from datetime import datetime
from calendar import monthrange
import os
# Create your views here.
User = get_user_model()

def notify(user=None, membre=None, titre=None, description=None):
    getter, setter = Notification.objects.get_or_create(user=user, membre=membre, titre=titre, description=description)
    if setter: return True
    return False

def provinceSelector():
    provinces = Province.objects.order_by('nom').exclude(nom=None)
    for prov in provinces:
        prov.membre = len(Membre.objects.filter(province=prov))
    return provinces

def demandeSuppression(request, id):
    user = request.user
    membre = Membre.objects.get(id=id)
    if membre.is_delete:
        membre.is_delete = False
        titre = "Annulation de la demande de suppression"
    else:
        membre.is_delete = True
        titre = "Demande de suppression"
    membre.save()
    notify(user=user, membre=membre, titre=titre)
    return redirect("membre-view", id=id)
#---------------------------------------------------------------------------------------------------------------------------

#Statistique:
def statistiqueMembre(an=False, mois=False, structure=None):
    today = datetime.today()
    if an == False: an = today.year
    if mois == False: mois = today.month
    denierJour = monthrange(an, mois)[1]
    fin = today.replace(year=an, month=mois, day=denierJour)
    debut = today.replace(year=an, month=mois, day=1)
    membres = Membre.objects.filter(mise_a_jour__gte=debut, mise_a_jour__lte=fin, structure=structure).exclude(nom=None)
    return int(len(membres))

def statistiqueMoto(an=False, mois=False, structure=None):
    today = datetime.today()
    if an == False: an = today.year
    if mois == False: mois = today.month
    denierJour = monthrange(an, mois)[1]
    fin = today.replace(year=an, month=mois, day=denierJour)
    debut = today.replace(year=an, month=mois, day=1)
    motos = Moto.objects.filter(mise_a_jour__gte=debut, mise_a_jour__lte=fin, structure=structure)
    return int(len(motos))

#Notification recupération
def myNotify(request):
    user = request.user
    if user.privilege5 or user.is_superuser:
        return Notification.objects.order_by('-id')
    else:
        data = Notification.objects.filter(user=user).order_by('-id')
        if user.membreId:
            membre = Membre.objects.get(id=user.membreId)
            data = Notification.objects.filter(user=user, membre=membre).order_by('-id')
    return data

#Securité
def security(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    user = request.user
    membre = Membre.objects.get(id=id)
    
    
    user = request.user
    if request.method == 'POST':
        if user.username == request.POST['pseudoA']:
            connecting = authenticate(username=request.POST['pseudoA'], password=request.POST['passA'])
            if connecting is not None:
                if request.POST['pseudoN']:
                    user.username = request.POST['pseudoN']
                if request.POST['passN']:
                    user.set_password(request.POST['passN'])
                user.save()
                message = 'mise à jour !'
                classe = 'alert alert-info'
                logout(request)
                return redirect("home")
    return render(request, 'app/membre.html', locals())

#Validation des membres
def validate(request, id):
    user = request.user
    membre = Membre.objects.get(id=id)
    
    if user.privilege2:
        if membre.is_validate2:
            membre.is_validate2 = False
        else:
            membre.is_validate2 = True

    if user.privilege3:
        if membre.is_validate3:
            membre.is_validate3 = False
        else:
            membre.is_validate3 = True

    if user.privilege5 or user.is_superuser:
        if membre.is_validate3:
            membre.is_validate2 = False
            membre.is_validate3 = False
        else:
            membre.is_validate1 = True
            membre.is_validate2 = True
            membre.is_validate3 = True

    membre.save()
    return redirect("home-session")

#---------------------------------------------------------------------------------------------------------------------------

#User session redirect liste of structures

def home(request):

    # redirection
    if not request.user.is_superuser and not request.user.privilege5:
        return redirect('home-session')

    if not request.user.membreId and request.user.is_superuser:
        province = Province.objects.create()
        ville = Ville.objects.create(province=province)
        membre = Membre.objects.create(user=request.user)
        membre.ville = ville
        membre.province = province
        membre.save()
        request.user.membreId = Membre.objects.last().id
        request.user.save()
    errors = Error.objects.filter(error404=True).last()
    if errors:
        message = 404
        return redirect("error")
    else:
        provinces = Province.objects.order_by('nom').exclude(nom=None)
        for prov in provinces:
            structures = Structure.objects.filter(province=prov).order_by('nom')
            for strct in structures:
                membres = len(Membre.objects.filter(structure=strct, is_delete=False, is_validate3=True))
                strct.membres = membres
            prov.structures = structures
    return render(request, 'app/home.html', locals())


# Add structure

def add_structure(request):
    button = 'Ajouter'
    activeAdd = 'show active'
    if request.method == 'POST':
        form = StructureIdentifyForm(request.POST, request.FILES)
        if form.is_valid():
            structure = form.save(commit=False)
            structure.save()
            msg = "Nouvelle structure ajouté !"
            classMsg = 'alert alert-info'
            return redirect('edit-structure', id=structure.id)
    else:
        form = StructureIdentifyForm()
    return render(request, 'app/structure.html', locals())


def ville_select(request, id):
    try:
        structure = Structure.objects.get(id=id)
        if structure.ville: return redirect('edit-structure', id=structure.id)
        provinces = Ville.objects.filter(province=structure.province).exclude(nom=None)
        if request.method == 'POST':
            try: ville = Ville.objects.get(nom=str(request.POST.get('ville')).upper())
            except: ville = Ville.objects.create(province=structure.province, nom=str(request.POST.get('ville')).upper())
            structure.ville = ville
            structure.save()
            return redirect("edit-structure", id=structure.id)
    except Exception as error:
        print(f"\n\n\n{error}\n\n\n")
    return render(request, 'app/ville-select.html', locals())


def ville_attr(request, id, sid):
    try:
        structure = Structure.objects.get(id=sid)
        ville = Ville.objects.get(id=id)
        structure.ville = ville
        structure.save()
    except Exception as error:
        pass
    return redirect('ville-select', id=structure.id)

def ville_attr_membre(request, id, idM):
    membre = Membre.objects.get(id=idM)
    ville = Ville.objects.get(id=id)
    membre.ville = ville
    membre.save()
    return redirect('membre-view', id=idM)

def antenne_attr_membre(request, id, idM):
    membre = Membre.objects.get(id=idM)
    antenne = Antenne.objects.get(id=id)
    membre.antenne = antenne
    membre.save()
    return redirect('membre-view', id=idM)

def structure_attr_membre(request, id, idM):
    membre = Membre.objects.get(id=idM)
    asbl = Structure.objects.get(id=id)
    membre.structure = asbl
    membre.save()
    return redirect('membre-view', id=idM)


def edit_structure(request, id):
    button = 'Modifier'
    activeEdit = 'show active'
    try:
        structure = Structure.objects.get(id=id)
        if not structure.ville:
            return redirect('ville-select', id=structure.id)
        if request.method == 'POST':
            form = StructureForm(request.POST, request.FILES, instance=structure)
            if form.is_valid(): form.save()
        else: form = StructureForm(instance=structure)

        structure.membres = len(Membre.objects.filter(structure=structure, is_delete=False))
        structure.proprietaires = len(Membre.objects.filter(structure=structure, titre='PROPRIETAIRE', is_delete=False))
        structure.motocyclistes = len(Membre.objects.filter(structure=structure, is_delete=False).exclude(titre='PROPRIETAIRE'))
    except: return redirect('home-app')
    return render(request, 'app/structure.html', locals())

def structures_liste(request):
    structures = Structure.objects.order_by('nom')
    for struct in structures:
        struct.membres = len(Membre.objects.filter(structure=struct, is_delete=False))
    return render(request, 'app/structures.html', locals())

#Home session
def session(request):
    #Session of user
    user = request.user
    structure = Structure.objects.filter(users=user).first()

    if structure:
        #Configuration
        messages = Communique.objects.order_by('-id')[0:3]
        if user.membreId:
            userMbr = Membre.objects.filter(id=user.membreId)
            for us in userMbr:
                userMembre = us
            if len(userMbr) != 0 and userMembre.ville:
                villeId = userMembre.ville.id

        notifications = myNotify(request)[0:3]
        antennes = Antenne.objects.filter(structure=structure).order_by('nom')
        membres = Membre.objects.filter(structure=structure, is_delete=False)
        
        #Traitement de la fonction
        today = datetime.today()
        an = today.year
        if not request.user.is_authenticated:
            return redirect('application')
        provincess = Province.objects.order_by('nom')
        nbr_moto = len(Moto.objects.filter(proprietaire__structure=structure))
        nbr_motard = len(Membre.objects.filter(structure=structure, qualite__icontains='MOTARD'))
        nbr_proprietaire = len(Membre.objects.filter(structure=structure,qualite='PROPRIETAIRE'))
        nbr_membre = len(Membre.objects.filter(structure=structure).exclude(nom=None))
        
        membresDeMois = statistiqueMembre(structure=structure)
        #Stat membre
        membreDuMois = {
            'janvier':statistiqueMembre(mois=1,structure=structure),
            'fevrier':statistiqueMembre(mois=2,structure=structure),
            'mars':statistiqueMembre(mois=3,structure=structure),
            'avril':statistiqueMembre(mois=4,structure=structure),
            'mai':statistiqueMembre(mois=5,structure=structure),
            'juin':statistiqueMembre(mois=6,structure=structure),
            'juillet':statistiqueMembre(mois=7,structure=structure),
            'aout':statistiqueMembre(mois=8,structure=structure),
            'septembre':statistiqueMembre(mois=9,structure=structure),
            'octobre':statistiqueMembre(mois=10,structure=structure),
            'novembre':statistiqueMembre(mois=11,structure=structure),
            'decembre':statistiqueMembre(mois=12,structure=structure)
        }
        #Stat moto
        motoDuMois = {
            'janvier':statistiqueMoto(mois=1,structure=structure),
            'fevrier':statistiqueMoto(mois=2,structure=structure),
            'mars':statistiqueMoto(mois=3,structure=structure),
            'avril':statistiqueMoto(mois=4,structure=structure),
            'mai':statistiqueMoto(mois=5,structure=structure),
            'juin':statistiqueMoto(mois=6,structure=structure),
            'juillet':statistiqueMoto(mois=7,structure=structure),
            'aout':statistiqueMoto(mois=8,structure=structure),
            'septembre':statistiqueMoto(mois=9,structure=structure),
            'octobre':statistiqueMoto(mois=10,structure=structure),
            'novembre':statistiqueMoto(mois=11,structure=structure),
            'decembre':statistiqueMoto(mois=12,structure=structure)
        }
        #print(membreDuMois)
    return render(request, 'app/index.html', locals())

#Home session by id
def sessionById(request, id):
    #Session of user
    user = request.user
    structure = Structure.objects.get(id=id)

    if structure:
        #Configuration
        messages = Communique.objects.order_by('-id')[0:3]
        if user.membreId:
            userMbr = Membre.objects.filter(id=user.membreId)
            for us in userMbr:
                userMembre = us
            if len(userMbr) != 0:
                villeId = userMembre.ville.id

        notifications = myNotify(request)[0:3]
        antennes = Antenne.objects.filter(structure=structure).order_by('nom')
        membres = Membre.objects.filter(structure=structure, is_delete=False)
        
        #Traitement de la fonction
        today = datetime.today()
        an = today.year
        if not request.user.is_authenticated:
            return redirect('application')
        provincess = Province.objects.order_by('nom')
        nbr_moto = len(Moto.objects.filter(proprietaire__structure=structure))
        nbr_motard = len(Membre.objects.filter(structure=structure, qualite__icontains='MOTARD'))
        nbr_proprietaire = len(Membre.objects.filter(structure=structure,qualite='PROPRIETAIRE'))
        nbr_membre = len(Membre.objects.filter(structure=structure).exclude(nom=None))
        
        membresDeMois = statistiqueMembre(structure=structure)
        #Stat membre
        membreDuMois = {
            'janvier':statistiqueMembre(mois=1,structure=structure),
            'fevrier':statistiqueMembre(mois=2,structure=structure),
            'mars':statistiqueMembre(mois=3,structure=structure),
            'avril':statistiqueMembre(mois=4,structure=structure),
            'mai':statistiqueMembre(mois=5,structure=structure),
            'juin':statistiqueMembre(mois=6,structure=structure),
            'juillet':statistiqueMembre(mois=7,structure=structure),
            'aout':statistiqueMembre(mois=8,structure=structure),
            'septembre':statistiqueMembre(mois=9,structure=structure),
            'octobre':statistiqueMembre(mois=10,structure=structure),
            'novembre':statistiqueMembre(mois=11,structure=structure),
            'decembre':statistiqueMembre(mois=12,structure=structure)
        }
        #Stat moto
        motoDuMois = {
            'janvier':statistiqueMoto(mois=1,structure=structure),
            'fevrier':statistiqueMoto(mois=2,structure=structure),
            'mars':statistiqueMoto(mois=3,structure=structure),
            'avril':statistiqueMoto(mois=4,structure=structure),
            'mai':statistiqueMoto(mois=5,structure=structure),
            'juin':statistiqueMoto(mois=6,structure=structure),
            'juillet':statistiqueMoto(mois=7,structure=structure),
            'aout':statistiqueMoto(mois=8,structure=structure),
            'septembre':statistiqueMoto(mois=9,structure=structure),
            'octobre':statistiqueMoto(mois=10,structure=structure),
            'novembre':statistiqueMoto(mois=11,structure=structure),
            'decembre':statistiqueMoto(mois=12,structure=structure)
        }
        #print(membreDuMois)
    return render(request, 'app/index.html', locals())

def antenneView(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    
    antenne = Antenne.objects.get(id=id)
    membres = Membre.objects.filter(antenne=antenne, is_validate3=True)
    return render(request, 'app/antenne-view.html', locals())

#Ajout d'antenne
def addAntenne(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    user = request.user
    try:
        hello = "Hello !"
        structure = Structure.objects.get(id=id)
        if request.method == 'POST':
            form = AntenneForm(request.POST)
            if form.is_valid():
                antenne = form.save(commit=False)
                antenne.structure = structure
                antenne.ville = structure.ville
                antenne.province = structure.province
                antenne.user = request.user
                antenne.save()
                classe = 'alert alert-info text-center'
                message = "Ajout d'antenne"
                return redirect('edit-antenne', id=antenne.id)
        else: 
            form = AntenneForm()
    except Exception as error: print(f"\n\n\n{error}\n\n\n")
    return render(request, 'app/add-antenne.html', locals())

def editAntenne(request,id):
    antenne = Antenne.objects.get(id=id)
    structure = antenne.structure
    form = AntenneForm(instance=antenne)
    if request.method == 'POST':
        form = AntenneForm(request.POST, instance=antenne)
        if form.is_valid():
            form.save()
    return render(request, 'app/add-antenne.html', locals())

def addCommunique(request):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        if userMembre.ville:
            villeId = userMembre.ville.id
        else:
            userMembre.ville = Ville.objects.get(id=1)
            userMembre.save()
            villeId = userMembre.ville.id
    
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    

    membre = None
    user = request.user
    if user.membreId:
        membre = Membre.objects.get(id=user.membreId)
    if request.method == 'POST':
        message = request.POST['message']
        getter, setter = Communique.objects.get_or_create(user=user, membre=membre, message=message)
        if setter:
            message = 'Envoyé !'
            classe = 'alert alert-success text-center'
        elif getter:
            message = 'Vous avez déjà envoyé !'
            classe = 'alert alert-danger text-center'
    return render(request, 'app/add-communique.html', locals())

def addFamily(request,id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    membre = Membre.objects.get(id=id)
    if request.method == 'POST':
        getter, setter = Famille.objects.get_or_create(
            user=user
            ,membre=membre
            ,beneficiere=request.POST['nom']
            ,qualite=request.POST['qualite']
            ,genre=request.POST['genre']
            ,annee=request.POST['annee']
        )
        if setter:
            message = 'Ajout d\'un membre de la famille'
            classe = 'alert alert-success text-center'
        elif getter:
            message = 'Ce membre est déjà ajouté'
            classe = 'alert alert-danger text-center'
    
    return render(request, 'app/add-family.html', locals())

def addMembre(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        try:
            villeId = userMembre.ville.id
        except Exception as error:
            print(f"\n\n\n{error}\n\n\n")
    notifications = myNotify(request)[0:3]
    provinces = provinceSelector()
    
    try:
        structure = Structure.objects.get(id=id)
        ville = structure.ville
        user = request.user
        antennes = Antenne.objects.filter(structure=structure)
        if request.method == 'POST':
            form = MembreForm(request.POST, request.FILES)
            if form.is_valid():
                membre = form.save(commit=False)
                membre.structure = membre.structure
                try:
                    membre.province = membre.structure.province
                except: pass
                membre.user = request.user
                membre.save()
                classe = 'alert alert-info text-center'
                message = f"Ajout du membre"
                notify(user=user, titre="Ajout d'un membre")
                return redirect('membre-view', id=membre.id)
            else:
                classe = 'alert alert-danger text-center'
                message = f"Le membre est déjà ajouter"
        else:
            antennes = Antenne.objects.filter(structure=structure)
            form = MembreForm(structure=structure)
    except Exception as error: print(f"\n\n\n{error}\n\n\n")
    return render(request, 'app/add-membre.html', locals())

def add_membre_from_fenamo(request):
    if request.method == 'POST':
        form = MembreFenamoForm(request.POST, request.FILES)
        if form.is_valid():
            membre = form.save(commit=False)
            try:
                membre.province = membre.ville.province
            except: pass
            membre.save()
            return redirect('membre-view', id=membre.id)
    else:
        form = MembreFenamoForm()
    return render(request, 'app/add-membre-form-fenamo.html', locals())

#Ajout d'une moto
def addMoto(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        try:
            villeId = userMembre.ville.id
        except Exception as error:
            print(f"\n\n\n{error}\n\n\n")
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    user = request.user
    membre = Membre.objects.get(id=id)
    structure = membre.structure
    print(f"\n\n\n{structure}\n\n\n")
    if request.method == 'POST':
        photo = None
        if len(request.FILES) != 0:
            photo = request.FILES['photo']
        debut = datetime.today()
        finAbonnement = debut.replace(year=debut.year+1)
        motosCity = Moto.objects.filter(ville=membre.ville)
        if len(motosCity) == 0:
            numero = 1
        else:
            dernier = motosCity[len(motosCity)-1]
            numero = dernier.numero.split(str(structure.province.sigle))
            numero = int(numero[0])+1
        #numero = str(numero).zfill(4)+'v'+str(membre.ville.id)
        if numero < 100:
            numero = str(numero).zfill(3)+str(membre.structure.province.sigle)
        else:
            numero = str(numero)+str(membre.province.sigle)
        setter = Moto.objects.create(
            user=user,structure=structure,proprietaire=membre,antenne=membre.antenne,ville=membre.ville,province=membre.province
            ,numero=numero, photo=photo,num_plaque=request.POST['plaque'],marque=request.POST['marque'],couleur=request.POST['couleur']
            ,abonnement=finAbonnement,num_chassie=request.POST['chassie'],num_moteur=request.POST['moteur']
            )
        notify(user=user, titre="Ajout d'une moto", description=f"Numéro:{numero}")
        message = "Mise à jour !"
        classe='alert alert-primary text-center'
    return render(request, 'app/add-moto.html', locals())

#Ajout d'une province
def addProvince(request):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    if request.method == 'POST':
        getter, setter = Province.objects.get_or_create(nom=request.POST.get('nom'), sigle=request.POST.get('sigle'))
        if setter:
            message = f"{request.POST['nom']} a été ajouté comme province"
            classe = 'alert alert-info text-center'
    return render(request, 'app/add-province.html', locals())

#Ajout d'une ville
def addVille(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    user = request.user
    province = Province.objects.get(id=id)
    if request.method == 'POST':
        getter, setter = Ville.objects.get_or_create(user=user, province=province, nom=request.POST['nom'])
        if setter:
            classe = 'alert alert-info text-center'
            message = 'Ajout d\'une ville dans la base des données'
            getter = len(Ville.objects.all())
            setter = Ville.objects.get(id=getter)
            notify(user=user, titre="Ajout d'une ville", description=f"Province:{setter.province.nom} Ville:{setter.nom}")
    return render(request, 'app/add-ville.html', locals())

def attributMoto(request, id):
    membre = Membre.objects.get(id=id)
    if request.method == 'POST':
        motoVerify = Moto.objects.filter(numero=request.POST['numero'])
        if len(motoVerify) != 0:
            moto = Moto.objects.get(numero=request.POST['numero'])
            moto.motard_id = id
            moto.save()
    return redirect("membre-view", id=id)

def contact(request):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    contacts = Contact.objects.order_by('-id')
    return render(request, 'app/contact.html', locals())

def contactView(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    contact = Contact.objects.get(id=id)
    contact.traiter = True
    contact.save()
    return render(request, 'app/contact-view.html', locals())

def deleteMoto(request,id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    moto = Moto.objects.get(id=id)
    moto.is_delete = True
    moto.save()
    notify(user=moto.user, titre="Suppression d'une moto", description=f"Numero:{moto.numero}")
    return redirect('membre-view', id=moto.proprietaire.id)


def deleteFamily(request, id):
    famille = Famille.objects.get(id=id)
    idMbr = famille.membre.id
    famille.delete()
    return redirect("membre-view", id=idMbr)


def editFamily(request,id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    famille = Famille.objects.get(id=id)
    membre = Membre.objects.get(id=famille.membre.id)
    if request.method == 'POST':
        famille.user = user
        famille.membre=membre
        famille.beneficiere=request.POST['nom']
        famille.qualite=request.POST['qualite']
        famille.genre=request.POST['genre']
        famille.annee=request.POST['annee']
        famille.save()
        message = 'Mise à jour !'
        classe = 'alert alert-success text-center'
    
    return render(request, 'app/add-family.html', locals())


def editMoto(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    moto = Moto.objects.get(id=id)
    membre = Membre.objects.get(id=moto.proprietaire.id)
    if request.method == 'POST':
        moto.num_plaque = request.POST['plaque']
        moto.num_chassie = request.POST['chassie']
        moto.num_moteur = request.POST['moteur']
        moto.marque = request.POST['marque']
        moto.couleur = request.POST['couleur']
        if len(request.FILES) != 0:
            moto.photo = request.FILES['photo']
        moto.save()
        message = "Mise à jour !"
        classe = 'alert alert-primary text-center'
        notify(user=moto.user, titre="Modification d'une moto", description=f"Numero:{moto.numero}")
    return render(request, 'app/add-moto.html', locals())


def errorPage(request):
    return render(request, 'app/pages-error-404.html', locals())

#Redirection to membre-view
def viewUser(request, id):
    return redirect('membre-view', id=id)

#Vue de membreerrorPage
def membre_view(request, id):
    if request.user.is_authenticated:
        try: structure = Structure.objects.filter(users=request.user).first()
        except: pass
        #Configuration
        messages = Communique.objects.order_by('-id')[0:3]
        user = request.user
        if user.membreId:
            userMembre = Membre.objects.get(id=user.membreId)
            if userMembre.ville:
                villeId = userMembre.ville.id
        notifications = myNotify(request)[0:3]
        antennes = Antenne.objects.order_by('nom')
        provinces = provinceSelector()
    
        user = request.user
        verify = User.objects.filter(membreId=id)
        if verify:
            membreUser = verify[0]
        
    membre = Membre.objects.get(id=id)
    villes = Ville.objects.filter(province=membre.province).exclude(nom=None)
    structures = Structure.objects.filter(province=membre.province)
    if not membre.ville or not membre.structure or not membre.antenne: 
        if request.user.is_authenticated: variante = 6
        else: variante = 12
    else: variante = 12

    if membre.ville:
        antennes = Antenne.objects.filter(structure__ville=membre.ville).exclude(nom=None)
    familles = Famille.objects.filter(membre=membre)
    #motos = len(Moto.objects.filter(proprietaire=membre, is_delete=False))
        
    verifyMoto = Moto.objects.filter(motard_id=membre.id)
    if len(verifyMoto) != 0:
        motoAttr = Moto.objects.get(motard_id=membre.id)
    
    naissance = membre.date_naissance
    today = datetime.today()
    age = today.year - naissance.year
    if request.method == 'POST':
        if 'modifier' in request.POST:
            membre.nom = request.POST['nom']
            membre.a_propos = request.POST['about']
            membre.date_naissance = datetime.strptime(request.POST['date'],'%d-%m-%Y')
            membre.genre = request.POST['genre']
            membre.titre = request.POST['titre']
            membre.fonction = request.POST['fonction']
            membre.comite = request.POST['comite']
            membre.nation = request.POST['nation']
            membre.brevet = request.POST['brevet']
            membre.etat_civil = request.POST['etat_civil']
            membre.epouse = request.POST['epouse']
            membre.adresse = request.POST['adresse']
            membre.telephone = request.POST['telephone']
            membre.mail = request.POST['mail']
            membre.categorie = request.POST['categorie']
            membre.permis = request.POST['permis']
            membre.qualite = request.POST['qualite']
            membre.autre_asbl = request.POST['autre_asbl']
            membre.numero_carte_d_electeur = request.POST['numero_carte_d_electeur']
            membre.numero_carte_de_membre = request.POST['numero_carte_de_membre']
            membre.nom_pere = request.POST['nom_pere']
            membre.nom_mere = request.POST['nom_mere']
            membre.village = request.POST['village']
            membre.chefferie = request.POST['chefferie']
            membre.territoire = request.POST['territoire']
            membre.province_origine = request.POST['province_origine']
            if len(request.FILES) != 0:
                membre.photo = request.FILES['photo']
            membre.save()
            notify(user=membre.user, membre=membre, titre="Motification d'un membre")
        elif 'envoyer' in request.POST:
            demande = request.POST['demande']
            getter, setter = Notification.objects.get_or_create(user=user, membre=membre, titre='Demande de modification', description=demande)
            if setter:
                message = 'Votre demande a été envoyer'
                classMessage = 'alert alert-info'
            elif getter:
                message = 'Votre demande a déjà été envoyer'
                classMessage = 'alert alert-info'
        elif 'privilege' in request.POST:
            if 'privilege1' in request.POST:
                membreUser.privilege1 = True
            else:
                membreUser.privilege1 = False

            if 'privilege2' in request.POST:
                membreUser.privilege2 = True
            else:
                membreUser.privilege2 = False

            if 'privilege3' in request.POST:
                membreUser.privilege3 = True
            else:
                membreUser.privilege3 = False

            if 'privilege4' in request.POST:
                membreUser.privilege4 = True
            else:
                membreUser.privilege4 = False

            if 'privilege5' in request.POST:
                membreUser.privilege5 = True
            else:
                membreUser.privilege5 = False
            membreUser.save()
    if request.user.is_authenticated:
        if verify:
            if membreUser.privilege1: checked1 = 'checked'
            if membreUser.privilege2: checked2 = 'checked'
            if membreUser.privilege3: checked3 = 'checked'
            if membreUser.privilege4: checked4 = 'checked'
            if membreUser.privilege5: checked5 = 'checked'
            notify(user=user, membre=membre, titre="Attribution des privilegès")
        motos = Moto.objects.filter(proprietaire=membre, is_delete=False)
        nbrMoto = len(motos)
    return render(request, 'app/membre.html', locals())

#Vue de la moto
def moto_view(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    moto = Moto.objects.get(id=id)
    if user.is_authenticated:
        if user.membreId:
            userMembre = Membre.objects.get(id=user.membreId)
            villeId = userMembre.ville.id
        notifications = myNotify(request)[0:3]
        antennes = Antenne.objects.order_by('nom')
        provinces = provinceSelector()
    
    membre = moto.proprietaire
    verify = len(User.objects.filter(membreId=id))
    if verify != 0:
        membreUser = User.objects.get(membreId=id)
    
    if moto.motard_id:
        motard = Membre.objects.get(id=moto.motard_id)
    return render(request, 'app/moto-view.html', locals())

#Vue de la liste des villes dans la province
def province_view(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId != None:
        uMbr = Membre.objects.filter(id=user.membreId)[0:1]
        for mbr in uMbr:
            userMembre = mbr
        #userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    user = request.user
    membre = Membre.objects.filter(id=id)
    for mbr in membre:
        membre = mbr
    #motos = len(Moto.objects.filter(proprietaire=membre, is_delete=False))
    verify = len(User.objects.filter(membreId=id))
    if verify != 0:
        membreUser = User.objects.get(membreId=id)
    
    province = Province.objects.get(id=id)
    villes = Ville.objects.filter(province=province).order_by('nom')
    return render(request, 'app/province-view.html', locals())

#Recherche des membres ou de la moto
def recherche(request):
    if request.user.is_authenticated:
        #Configuration
        messages = Communique.objects.order_by('-id')[0:3]
        user = request.user
        if user.membreId:
            userMembre = Membre.objects.get(id=user.membreId)
            villeId = userMembre.ville.id
        notifications = myNotify(request)[0:3]
        antennes = Antenne.objects.order_by('nom')
        provinces = provinceSelector()
        
        try:
            membre = Membre.objects.get(id=user.membreId)
            #motos = len(Moto.objects.filter(proprietaire=membre, is_delete=False))
            verify = len(User.objects.filter(membreId=membre.id))
            if verify != 0:
                membreUser = User.objects.get(membreId=membre.id)
        except:
            pass
    
    if request.method == 'POST':
        if request.POST['search']:
            champ = request.POST['champ']
            if len(champ) != 0:
                membres = Membre.objects.filter(nom__icontains=champ).order_by('nom','-mise_a_jour')
                motos = Moto.objects.filter(numero__icontains=str(champ))
                print(f"\n\n\n{motos}\n\n\n")
                if len(membres) == 0 and len(motos) == 0:
                    membres = {}
                    message = f'Aucun resultat !'
                    classe = 'alert alert-danger text-center'
            else:
                membres = {}
                message = 'Aucun resultat !'
                classe = 'alert alert-danger text-center'
    return render(request, 'app/resultats.html', locals())

#Afficher la liste des antennes dans une ville
def ville_view(request, id):
    
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    structure = Structure.objects.filter(users=user).first()
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.filter(structure=structure).order_by('nom')
    provinces = provinceSelector()
    
    user = request.user
    membre = Membre.objects.filter(id=id)
    if membre:
        membre = membre[0]
    #motos = len(Moto.objects.filter(proprietaire=membre, is_delete=False))
    verify = len(User.objects.filter(membreId=id))
    if verify != 0:
        membreUser = User.objects.get(membreId=id)
    
    ville = Ville.objects.get(id=id)
    if user.is_superuser or user.privilege5:
        membres = Membre.objects.filter(ville=ville, is_delete=False).order_by('nom','antenne')
    else:
        if user.privilege1 or user.privilege2 or user.privilege3:
            membres = Membre.objects.filter(ville=ville, is_delete=False, is_validate1=True).order_by('nom','antenne')
        elif user.privilege4:
            membres = Membre.objects.filter(ville=ville, is_delete=False, is_validate3=True).order_by('nom','antenne')
    return render(request, 'app/ville-view.html', locals())


#Afficher la liste des membres
def membreListe(request):
    
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        if userMembre.ville:
            villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    user = request.user
    membre = Membre.objects.filter(id=user.membreId)
    if membre:
        membre = membre[0]
    membreUser = User.objects.get(membreId=user.membreId)
    
    try:
        ville = membre.ville
    except: pass
    if user.is_superuser or user.privilege5:
        membres = Membre.objects.filter(is_delete=False).order_by('user__username','antenne', 'nom')
    else:
        if user.privilege1 or user.privilege2:
            membres = Membre.objects.filter(is_delete=False, is_validate1=True).order_by('user__username','antenne', 'nom')
        elif user.privilege3:
            membres = Membre.objects.filter(is_delete=False, is_validate1=True, is_validate2=True).order_by('user__username','antenne', 'nom')
        elif user.privilege4:
            membres = Membre.objects.filter(is_delete=False, is_validate3=True).order_by('user__username','antenne', 'nom')
    return render(request, 'app/membre-list.html', locals())


def notificationsView(request):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    user = request.user
    membre = Membre.objects.get(id=user.membreId)
    #motos = len(Moto.objects.filter(proprietaire=membre, is_delete=False))
    verify = len(User.objects.filter(membreId=user.membreId))
    if verify != 0:
        membreUser = User.objects.get(membreId=user.membreId)
    
    notifications = myNotify(request)[0:3]
    notifys = myNotify(request)
    return render(request, 'app/notifications.html', locals())

def listMessage(request):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()

    
    #Traitement des données
    communiques = Communique.objects.order_by('-id')
    return render(request, 'app/list-message.html', locals())

def messageView(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    
    message = Communique.objects.get(id=id)
    reactions = Reaction.objects.filter(communique=message)
    return render(request, 'app/message-view.html', locals())

def site(request):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()



    #Intitulé
    intit = "Ajouté l'article"

    #Add article
    if request.method == 'POST':
        titre = request.POST.get('titre')
        code = request.POST.get('code')
        description = request.POST.get('description')
    
        if len(request.FILES) == 0:
            image = None
            message = "Echec de selection d'image"
            classe = 'alert alert-danger text-center'
        else:
            image = request.FILES.get('image')
            try:
                verify = Article.objects.get(titre=titre)
                verify = True
            except:
                verify = False

            if verify == False:
                galery = Galery.objects.create(image=image, principale=True)
                article = Article.objects.create(titre=titre,integration_code=code,image=image,description=description)
                article.galery.add(galery)
                article.save()
                message = "Publication de l'article effectuée !"
                classe = 'alert alert-info text-center'
            else:
                message = "Cet article a déjà été publié"
                classe = 'alert alert-danger text-center'
        
    
    #Articles
    articles = Article.objects.order_by('-id')
    return render(request, 'app/site.html', locals())

def article(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.get(id=user.membreId)
        villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    
    #Intitulé
    intit = "Modifier l'article"
    
    #Article edit
    article = Article.objects.get(id=id)
    if request.method == 'POST':
        article.titre = request.POST.get('titre')
        article.description = request.POST.get('description')
        if len(request.FILES) != 0:
            if article.image: 
                try: os.remove(article.image.path)
                except: pass
            article.image = request.FILES.get('image')
        message = "Mise à jour de l'article !"
        classe = 'alert alert-info text-center'
        article.save()
    
    #Articles
    articles = Article.objects.order_by('-id')
    return render(request, 'app/site.html', locals())

def deleteArticle(request, id):
    article = Article.objects.get(id=id)
    try: os.remove(article.image.path)
    except: pass
    article.delete()
    return redirect("site")