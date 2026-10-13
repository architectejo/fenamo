from django.shortcuts import redirect, render
from virtrine.models import Article, Config, Contact
from virtrine.forms import ConfigForm
from coptapp.forms import AssociationMembreIdentifyForm

from datetime import date

from compte.permissions import editeur_requis

# Create your views here.

def actualy(request):
    nbr = len(Config.objects.all())
    if nbr != 0:
        affiche = Config.objects.get(id=nbr)
    else:
        affiche = {}
    articles = Article.objects.order_by('-id')
    classActualy = 'active'
    return render(request, 'site/blog.html', locals())

def about(request):
    nbr = len(Config.objects.all())
    if nbr != 0:
        affiche = Config.objects.get(id=nbr)
    else:
        affiche = {}
    classAbout = 'active'
    return render(request, 'site/about.html', locals())

def article(request, id):
    art = Article.objects.get(id=id)
    nbr = len(Config.objects.all())
    if nbr != 0:
        affiche = Config.objects.get(id=nbr)
    else:
        affiche = {}
    articles = Article.objects.order_by('-id')[0:5]
    classArticle = 'active'
    return render(request, 'site/blog-details.html', locals())

def home(request):
    if request.method == 'POST':
        nom = (request.POST.get('nom') or '').strip()
        mail = (request.POST.get('mail') or '').strip()
        datePost = request.POST.get('date') or None
        raison = request.POST.get('raison') or ''
        phone = request.POST.get('phone') or ''
        description = request.POST.get('description') or ''
        if not nom or not mail:
            message = "Indiquez votre nom et votre adresse e-mail."
            classe = 'alert alert-danger text-center'
            affiche = Config.objects.last()
            articles = Article.objects.order_by('-id')[0:12]
            classHome = 'active'
            return render(request, "site/index.html", locals(), status=400)
        getter, setter = Contact.objects.get_or_create(nom=nom, mail=mail, date=datePost, raison=raison, phone=phone,description=description)
        if setter:
            message = "Envoi effectué avec succès"
            classe = 'alert alert-primary text-center'
        elif getter:
            message = "Message déjà envoyer"
            classe = 'alert alert-danger text-center'
    try:
        affiche = Config.objects.last()

    except:
        affiche = Config.objects.create()
    articles = Article.objects.order_by('-id')[0:12]
    classHome = 'active'
    return render(request, "site/index.html", locals())

#______________Configuration

@editeur_requis
def config(request):
    nbr = len(Config.objects.all())
    if nbr != 0:
        affiche = Config.objects.get(id=nbr)
    else:
        affiche = {}
        
    try:
        conf = Config.objects.last()
    except:
        conf = Config.objects.create()

    if request.method == 'POST':
        form = ConfigForm(request.POST, request.FILES, instance=conf)
        if form.is_valid():
            form.save()
    else:
        form = ConfigForm(instance=conf)
    return render(request, 'site/config.html', locals())

def portail(request):
    nbr = len(Config.objects.all())
    if nbr != 0:
        affiche = Config.objects.get(id=nbr)
    else:
        affiche = {}
        
    try:
        conf = Config.objects.last()
    except:
        conf = Config.objects.create()

    if request.method == 'POST':
        form = AssociationMembreIdentifyForm(request.POST,request.FILES)
        if form.is_valid():
            assoc = form.save(commit=False)
            assoc.save()
            message = "Votre association a été enregistré !"
            classe = 'alert alert-success text-center'
            return redirect('edit-structure', id=assoc.id)
    else:
        form = AssociationMembreIdentifyForm()
    return render(request, 'site/portail.html', locals())


def politique(request):
    today = date.today()
    return render(request, 'site/politique.html', locals())