from django.core.exceptions import PermissionDenied
from django.contrib import messages as contrib_messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from compte.models import JournalAction
from compte.services.comptes import compte_du_membre
from compte.services.journal import journaliser
from compte.services.privileges import attribuer_privileges
from coptapp.services import transitions
from coptapp.services.actions import ACTIONS_SUPPRESSION, changer_suppression, rattacher, traiter_suppression_membre
from coptapp.services.transitions import EtatIncoherent
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_GET, require_POST
from coptapp.models import *
from django.contrib.auth import authenticate, get_user_model, logout
from virtrine.models import Article, Contact, Galery
from coptapp.forms import *
from coptapp.views.modales import rendre_formulaire
from coptapp.validators import erreur_image
from compte.permissions import editeur_requis, referentiel_ecriture_requis
from compte.services.droits import (
    antennes_du_perimetre, associations_du_compte, cible_rattachable, droits_membre, engin_pour, engins_visibles,
    membre_et_droits, membre_pour, membres_du_perimetre, provinces_du_perimetre, villes_du_perimetre, voit_tout,
)
from coptapp.services.geographie import antenne_depuis_ville, completer_antenne, rattacher_antenne, rattacher_ville
from coptapp.services.engins import (
    CoordinationInconnue, EnginDejaEnregistre, attribuer_engin, enregistrer_engin, lister_engins,
)
from coptapp.services.fiche_membre import contexte_fiche
from coptapp.services.transitions import compter_validables, valider_tous
from coptapp.services.membres import (
    Q_LONGUEUR_MAX, choix_filtres, demander_modification, lister_membres, membres_filtres, modifier_membre,
)

RESULTATS_MAX = 50
from fenamo.htmx import reponse_succes, veut_fragment
from django.utils.http import url_has_allowed_host_and_scheme
from datetime import datetime
from calendar import monthrange
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

@require_POST
def demandeSuppression(request, id):
    """Suppression logique d'un membre (F-25), par action explicite (champ ``action``) et motif (champ ``motif``).

    ``action`` : ``demander`` (dépose une demande), ``annuler`` (annule la demande en cours), ``executer`` (SU et
    privilege5 : suppression logique), ``restaurer`` (SU et privilege5 : annule une suppression). Motif obligatoire
    sauf pour ``annuler`` (500 caractères au plus). 400 si l'action manque ou est inconnue ; 404 hors périmètre (un
    membre supprimé n'est visible que de qui peut le restaurer) ; 403 sans droit ; 409 si l'action ne correspond pas
    à l'état courant du membre (déjà supprimé, demande déjà faite…) ; sinon message et retour à la fiche.
    """
    user = request.user
    action = request.POST.get('action')
    if action not in ACTIONS_SUPPRESSION:
        return HttpResponseBadRequest(_("Action de suppression manquante ou inconnue."))
    membre = membre_pour(user, id, 'peut_demander_suppression', supprimes_visibles=True)
    try:
        resultat = traiter_suppression_membre(user, membre, action, request.POST.get('motif'))
    except EtatIncoherent:
        return HttpResponse(_("L'état du membre a changé : rechargez la fiche."), status=409)
    messages_resultat = {
        'motif_requis': (contrib_messages.error, _("Indiquez le motif de la suppression.")),
        'motif_trop_long': (contrib_messages.error, _("Le motif est limité à 500 caractères.")),
        'supprime': (contrib_messages.success, _("Membre supprimé.")),
        'restaure': (contrib_messages.success, _("Suppression annulée.")),
        'demande': (contrib_messages.success, _("Demande de suppression envoyée.")),
        'demande_annulee': (contrib_messages.success, _("Demande de suppression annulée.")),
    }
    ajouter, texte = messages_resultat[resultat]
    ajouter(request, texte)
    if resultat not in ('motif_requis', 'motif_trop_long'):
        notify(user=user, membre=membre, titre=str(texte))
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
    from compte.services.perimetre import notifications_du_perimetre
    return notifications_du_perimetre(request.user).order_by('-id')

#Validation des membres
def _retour(request, defaut):
    """Redirige vers la page d'où vient la demande (champ ``next`` ou en-tête Referer), si elle est du même site."""
    cible = request.POST.get('next') or request.META.get('HTTP_REFERER', '')
    if cible and url_has_allowed_host_and_scheme(cible, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(cible)
    return redirect(defaut)


@require_POST
def validate(request, id):
    """Valide un membre (F-23). Idempotente : elle ne fait que VALIDER, jamais dévalider.

    404 hors périmètre, 403 si le compte ne valide à aucun niveau. Règles de `etapes_a_valider` : étape précédente
    exigée, jamais sa propre fiche ni ses propres saisies. Si rien n'est à valider pour ce compte, rien ne change et
    rien n'est journalisé. Le renvoi au niveau inférieur, avec motif obligatoire, est une action distincte (à venir).
    Retour à la page d'origine.
    """
    user = request.user
    membre = get_object_or_404(membres_du_perimetre(user), id=id)
    if not droits_membre(user)['peut_valider']:
        raise PermissionDenied
    if not transitions.valider(user, membre):
        contrib_messages.info(request, _("Rien à valider pour vous sur ce membre."))
    return _retour(request, 'liste-membre')

@require_POST
def validerTous(request):
    """« Valider tout le monde » : valide, à l'étape de l'auteur, tous les membres de son périmètre et des filtres de la liste (POST :
    q, etat, qualite, antenne, association), au plus VALIDER_TOUS_PLAFOND par appel (100 par défaut). 403 si l'auteur ne valide aucune étape. Requête HTMX : 204 avec
    toast et événement ``membresMaj`` (la liste se rafraîchit) ; sinon message et retour à la page d'origine."""
    user = request.user
    if not droits_membre(user)['peut_valider_tous']:
        raise PermissionDenied
    compte_rendu = valider_tous(user, request.POST)
    message = _("%(n)s membre(s) validé(s).") % {'n': compte_rendu['valides']}
    if compte_rendu['restants']:
        message += ' ' + _("%(n)s restant(s) : relancez la validation.") % {'n': compte_rendu['restants']}
    if veut_fragment(request):
        return reponse_succes(message, evenements=['membresMaj'])
    contrib_messages.success(request, message)
    return _retour(request, 'liste-membre')


@require_POST
def renvoyer(request, id):
    """Renvoie un membre à l'auteur de la saisie avec un motif obligatoire (F-23). POST + CSRF ; 404 hors périmètre, 403 sans droit
    de validateur sur ce membre ; motif vide : message d'erreur, rien ne change. Retour à la page d'origine."""
    user = request.user
    membre = get_object_or_404(membres_du_perimetre(user), id=id)
    resultat = transitions.renvoyer(user, membre, request.POST.get('motif', ''))
    if resultat == 'renvoye':
        contrib_messages.success(request, _("Fiche renvoyée à son auteur avec le motif."))
    else:
        contrib_messages.error(request, _("Indiquez le motif du renvoi (500 caractères au plus)."))
    return _retour(request, 'liste-membre')

#---------------------------------------------------------------------------------------------------------------------------

#User session redirect liste of structures

# Add structure

@referentiel_ecriture_requis
def add_structure(request):
    button = 'Ajouter'
    activeAdd = 'show active'
    if request.method == 'POST':
        form = AssociationMembreIdentifyForm(request.POST, request.FILES)
        if form.is_valid():
            structure = form.save(commit=False)
            structure.save()
            msg = "Nouvelle association membre ajoutée !"
            classMsg = 'alert alert-info'
            return redirect('edit-structure', id=structure.id)
        return rendre_formulaire(request, 'structure', locals(), status=400, page='app/structure.html')
    else:
        form = AssociationMembreIdentifyForm()
    return rendre_formulaire(request, 'structure', locals(), page='app/structure.html')


@referentiel_ecriture_requis
def ville_select(request, id):
    structure = get_object_or_404(associations_du_compte(request.user), id=id)  # 404 hors du périmètre du compte
    if structure.ville:
        return redirect('edit-structure', id=structure.id)
    provinces = Ville.objects.filter(province=structure.province).exclude(nom=None)
    if request.method == 'POST':
        nom = str(request.POST.get('ville') or '').strip().upper()
        if not nom:
            message = _("Indiquez l'antenne.")
            classe = 'alert alert-danger text-center'
            return render(request, 'app/ville-select.html', locals(), status=400)
        # une ville homonyme d'une AUTRE coordination n'est jamais réutilisée
        ville = (Ville.objects.filter(nom=nom, province=structure.province).first()
                 or Ville.objects.create(province=structure.province, nom=nom))
        rattacher_ville(request.user, structure, ville)
        return redirect("edit-structure", id=structure.id)
    return render(request, 'app/ville-select.html', locals())


@referentiel_ecriture_requis
@require_POST
def ville_attr(request, id, sid):
    """Rattache l'association membre `sid` (de son périmètre : 404 sinon) à la ville `id` de SA coordination (404 sinon)."""
    structure = get_object_or_404(associations_du_compte(request.user), id=sid)
    if structure.province_id is None:
        raise Http404  # sans coordination, aucune ville ne lui est rattachable
    rattacher_ville(request.user, structure, get_object_or_404(Ville.objects.filter(province=structure.province), id=id))
    return redirect('ville-select', id=structure.id)

def _rattacher_membre(request, idM, champ, modele, id_cible):
    """Rattache le membre `idM` à la cible `id_cible` (de `modele`) : membre visible (404), droit de modifier (403),
    PUIS cible existante (404) et gérable (403). Le membre est contrôlé avant la cible : pas d'énumération."""
    membre = membre_pour(request.user, idM, 'peut_modifier')
    cible = get_object_or_404(modele, id=id_cible)
    if not cible_rattachable(request.user, champ, cible):
        raise PermissionDenied
    if champ == 'ville':
        rattacher_ville(request.user, membre, cible)  # ville ET antenne, une seule transaction
    elif champ == 'antenne':
        rattacher_antenne(request.user, membre, cible)
    else:
        rattacher(request.user, membre, champ, cible)
    return redirect('membre-view', id=idM)


@require_POST
def ville_attr_membre(request, id, idM):
    return _rattacher_membre(request, idM, 'ville', Ville, id)


@require_POST
def antenne_attr_membre(request, id, idM):
    return _rattacher_membre(request, idM, 'antenne', Antenne, id)


@require_POST
def structure_attr_membre(request, id, idM):
    return _rattacher_membre(request, idM, 'structure', AssociationMembre, id)


@referentiel_ecriture_requis
def edit_structure(request, id):
    button = 'Modifier'
    activeEdit = 'show active'
    structure = get_object_or_404(AssociationMembre, id=id)
    if not structure.ville:
        return redirect('ville-select', id=structure.id)
    if request.method == 'POST':
        form = AssociationMembreForm(request.POST, request.FILES, instance=structure)
        if form.is_valid():
            form.save()
            message = _("Association enregistrée.")
            classe = 'alert alert-info'
        else:
            statut_formulaire = 400
    else:
        form = AssociationMembreForm(instance=structure)
    membres_association = Membre.objects.filter(structure=structure).exclude(etat='supprime')
    structure.membres = membres_association.count()
    structure.proprietaires = membres_association.filter(titre='PROPRIETAIRE').count()
    structure.motocyclistes = membres_association.exclude(titre='PROPRIETAIRE').count()
    return rendre_formulaire(request, 'structure', locals(), status=locals().get('statut_formulaire', 200), page='app/structure.html')

def structures_liste(request):
    """Associations membres du compte (toutes pour SU / privilege5)."""
    structures = list(associations_du_compte(request.user).order_by('nom'))
    for struct in structures:
        struct.membres = membres_du_perimetre(request.user).filter(structure=struct).count()
    return render(request, 'app/structures.html', locals())

#Home session
def session(request):
    #Session of user
    user = request.user
    structure = AssociationMembre.objects.filter(users=user).first()

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
        membres = membres_du_perimetre(user).filter(structure=structure)
        
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
    structure = get_object_or_404(associations_du_compte(user), id=id)

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
        membres = membres_du_perimetre(user).filter(structure=structure)
        
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
    user = request.user
    antenne = get_object_or_404(antennes_du_perimetre(user), id=id)
    membres = membres_du_perimetre(user).filter(antenne=antenne, etat='actif')
    return render(request, 'app/antenne-view.html', locals())

#Ajout d'antenne
@referentiel_ecriture_requis
def addAntenne(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    userMembre = Membre.objects.filter(id=user.membreId).first() if user.membreId else None
    villeId = userMembre.ville_id if userMembre else None
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    user = request.user
    structure = get_object_or_404(AssociationMembre, id=id)
    if request.method == 'POST':
        form = AntenneForm(request.POST)
        if form.is_valid():
            antenne = form.save(commit=False)
            antenne.structure = structure
            antenne.coordination = antenne.coordination or structure.province  # choisie dans le formulaire, sinon celle de l'association
            antenne.user = request.user
            antenne.save()
            return redirect('edit-antenne', id=antenne.id)
    else:
        form = AntenneForm()
    return rendre_formulaire(request, 'antenne', locals())

@referentiel_ecriture_requis
def editAntenne(request,id):
    antenne = get_object_or_404(Antenne, id=id)
    structure = antenne.structure
    form = AntenneForm(instance=antenne)
    if request.method == 'POST':
        form = AntenneForm(request.POST, instance=antenne)
        if form.is_valid():
            form.save()
    return rendre_formulaire(request, 'antenne', locals())

@editeur_requis
def addCommunique(request):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    if user.membreId:
        userMembre = Membre.objects.filter(id=user.membreId).first()
        if userMembre and userMembre.ville:
            villeId = userMembre.ville.id
    
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    

    membre = None
    user = request.user
    if user.membreId:
        membre = Membre.objects.filter(id=user.membreId).first()
    if request.method == 'POST':
        message = (request.POST.get('message') or '').strip()
        if not message:
            message = _("Écrivez le communiqué.")
            classe = 'alert alert-danger text-center'
            return rendre_formulaire(request, 'communique', locals(), status=400)
        getter, setter = Communique.objects.get_or_create(user=user, membre=membre, message=message)
        if setter:
            message = _('Envoyé !')
            classe = 'alert alert-success text-center'
        elif getter:
            message = _('Vous avez déjà envoyé !')
            classe = 'alert alert-danger text-center'
    return rendre_formulaire(request, 'communique', locals())

def addFamily(request,id):
    user = request.user
    membre = membre_pour(user, id, 'peut_ajouter_famille')
    if request.method == 'POST':
        formulaire = FamilleForm(request.POST)
        if not formulaire.is_valid():
            message = erreurs_en_texte(formulaire)
            classe = 'alert alert-danger text-center'
            return rendre_formulaire(request, 'famille', locals(), status=400)
        donnees = formulaire.cleaned_data
        getter, setter = Famille.objects.get_or_create(
            user=user
            ,membre=membre
            ,beneficiere=donnees['nom']
            ,qualite=donnees['qualite']
            ,genre=donnees['genre']
            ,annee=donnees['annee']
        )
        if setter:
            message = "Ajout d'un membre de la famille"
            classe = 'alert alert-success text-center'
        elif getter:
            message = 'Ce membre est déjà ajouté'
            classe = 'alert alert-danger text-center'
    return rendre_formulaire(request, 'famille', locals())

def addMembre(request, id):
    """Ajout d'un membre à l'association `id` : association du compte (404 sinon), droit de créer (403 sinon)."""
    user = request.user
    structure = get_object_or_404(associations_du_compte(user), id=id)
    if not droits_membre(user)['peut_creer_membre']:
        raise PermissionDenied
    ville = structure.ville
    antennes = Antenne.objects.filter(structure=structure)
    if request.method == 'POST':
        form = MembreForm(request.POST, request.FILES, structure=structure)
        if form.is_valid():
            membre = form.save(commit=False)
            membre.structure = structure
            membre.province = structure.province
            membre.user = user
            membre.save()
            completer_antenne(membre)
            classe = 'alert alert-info text-center'
            message = "Ajout du membre"
            notify(user=user, titre="Ajout d'un membre")
            return redirect('membre-view', id=membre.id)
        classe = 'alert alert-danger text-center'
        message = "Le membre est déjà ajouter"
    else:
        form = MembreForm(structure=structure)
    return rendre_formulaire(request, 'membre', locals())

def add_membre_from_fenamo(request):
    """Ajout d'un membre hors association : réservé à qui voit tout (SU, privilege5), jamais en lecture seule."""
    user = request.user
    if not (voit_tout(user) and droits_membre(user)['peut_creer_membre']):
        raise PermissionDenied
    if request.method == 'POST':
        form = MembreFenamoForm(request.POST, request.FILES)
        if form.is_valid():
            membre = form.save(commit=False)
            if membre.ville:
                membre.province = membre.ville.province
            membre.user = user
            membre.save()
            completer_antenne(membre)
            return redirect('membre-view', id=membre.id)
    else:
        form = MembreFenamoForm()
    return rendre_formulaire(request, 'membre-form-fenamo', locals())

#Ajout d'une moto
def addMoto(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    userMembre = Membre.objects.filter(id=user.membreId).first() if user.membreId else None
    villeId = userMembre.ville_id if userMembre else None
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    user = request.user
    membre = membre_pour(user, id, 'peut_ajouter_engin')
    structure = membre.structure
    if request.method == 'POST':
        photo = request.FILES.get('photo')
        erreur_photo = erreur_image(photo) if photo else None
        if erreur_photo:
            message = erreur_photo
            classe = 'alert alert-danger text-center'
            return rendre_formulaire(request, 'moto', locals(), status=400)
        formulaire = EnginForm(request.POST)
        if not formulaire.is_valid():
            message = erreurs_en_texte(formulaire)
            classe = 'alert alert-danger text-center'
            return rendre_formulaire(request, 'moto', locals(), status=400)
        donnees = formulaire.cleaned_data
        try:
            engin = enregistrer_engin(membre, user, {
                'num_plaque': donnees['plaque'], 'marque': donnees['marque'], 'couleur': donnees['couleur'],
                'num_chassie': donnees['chassie'], 'num_moteur': donnees['moteur']}, photo=photo)
        except CoordinationInconnue:
            message = _("La coordination provinciale du membre est inconnue : l'engin ne peut pas être numéroté.")
            classe = 'alert alert-danger text-center'
            return rendre_formulaire(request, 'moto', locals(), status=400)
        except EnginDejaEnregistre:
            message = _("Cet engin est déjà enregistré (même numéro de châssis et de moteur).")
            classe = 'alert alert-danger text-center'
            return rendre_formulaire(request, 'moto', locals(), status=400)
        numero = engin.numero
        notify(user=user, titre="Ajout d'une moto", description=f"Numéro:{numero}")
        message = "Mise à jour !"
        classe='alert alert-primary text-center'
    return rendre_formulaire(request, 'moto', locals())

#Ajout d'une province
@referentiel_ecriture_requis
def addProvince(request):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    userMembre = Membre.objects.filter(id=user.membreId).first() if user.membreId else None
    villeId = userMembre.ville_id if userMembre else None
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    if request.method == 'POST':
        nom_province = (request.POST.get('nom') or '').strip()
        if not nom_province:
            message = _("Indiquez le nom de la coordination provinciale.")
            classe = 'alert alert-danger text-center'
            return rendre_formulaire(request, 'province', locals(), status=400)
        code = Province.normaliser_code(request.POST.get('code'))
        ordre_texte = (request.POST.get('ordre') or '').strip()
        if code and (len(code) > 5 or Province.objects.filter(code=code).exists()):
            message = _("Ce code officiel est trop long (5 caractères au plus) ou déjà utilisé.")
            classe = 'alert alert-danger text-center'
            return rendre_formulaire(request, 'province', locals(), status=400)
        if ordre_texte and not (ordre_texte.isdigit() and int(ordre_texte) <= 999):
            message = _("L'ordre d'affichage est un nombre entier de 0 à 999.")
            classe = 'alert alert-danger text-center'
            return rendre_formulaire(request, 'province', locals(), status=400)
        getter, setter = Province.objects.get_or_create(nom=nom_province, sigle=request.POST.get('sigle'),
                                                        defaults={'code': code, 'ordre': int(ordre_texte) if ordre_texte else None})
        if setter:
            message = _("%(nom)s a été ajoutée comme coordination provinciale.") % {'nom': nom_province}
            classe = 'alert alert-info text-center'
    return rendre_formulaire(request, 'province', locals())

#Ajout d'une ville
@referentiel_ecriture_requis
def addVille(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    userMembre = Membre.objects.filter(id=user.membreId).first() if user.membreId else None
    villeId = userMembre.ville_id if userMembre else None
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    user = request.user
    province = get_object_or_404(Province, id=id)
    if request.method == 'POST':
        nom_ville = (request.POST.get('nom') or '').strip()
        if not nom_ville:
            message = _("Indiquez le nom de l'antenne.")
            classe = 'alert alert-danger text-center'
            return rendre_formulaire(request, 'ville', locals(), status=400)
        ville, cree = Ville.objects.get_or_create(user=user, province=province, nom=nom_ville)
        antenne_depuis_ville(ville, creer=True)  # toute ville a son antenne
        if cree:
            classe = 'alert alert-info text-center'
            message = _("Antenne ajoutée à la coordination provinciale.")
            notify(user=user, titre=_("Ajout d'une antenne"),
                   description=f"{_('Coordination')} : {ville.province.nom} ; {_('antenne')} : {ville.nom}")
    return rendre_formulaire(request, 'ville', locals())

@require_POST
def attributMoto(request, id):
    """Attribue un motard (le membre `id`) à l'engin dont le numéro est envoyé (F-33) : voir `attribuer_engin`."""
    membre = membre_pour(request.user, id, 'peut_ajouter_engin')
    resultat = attribuer_engin(request.user, membre, request.POST.get('numero'))
    ajouter, texte = {
        'numero_requis': (contrib_messages.error, _("Indiquez le numéro de l'engin.")),
        'introuvable': (contrib_messages.error, _("Aucun engin ne porte ce numéro.")),
        'ambigu': (contrib_messages.error, _("Plusieurs engins portent ce numéro : attribution impossible.")),
        'attribue': (contrib_messages.success, _("Engin attribué.")),
    }[resultat]
    ajouter(request, texte)
    return redirect("membre-view", id=id)


@editeur_requis
def contact(request):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    userMembre = Membre.objects.filter(id=user.membreId).first() if user.membreId else None
    villeId = userMembre.ville_id if userMembre else None
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    contacts = Contact.objects.order_by('-id')
    return render(request, 'app/contact.html', locals())

@editeur_requis
def contactView(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    userMembre = Membre.objects.filter(id=user.membreId).first() if user.membreId else None
    villeId = userMembre.ville_id if userMembre else None
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    contact = get_object_or_404(Contact, id=id)
    if request.method == 'POST':
        contact.traiter = True
        contact.save()
    return render(request, 'app/contact-view.html', locals())

@require_POST
def deleteMoto(request,id):
    moto = engin_pour(request.user, id, 'peut_supprimer_engin')
    changer_suppression(request.user, moto, True)
    notify(user=moto.user, titre="Suppression d'une moto", description=f"Numero:{moto.numero}")
    return redirect('membre-view', id=moto.proprietaire.id)

@require_POST
def deleteFamily(request, id):
    famille = get_object_or_404(Famille, id=id)
    membre_pour(request.user, famille.membre_id, 'peut_supprimer_famille')
    idMbr = famille.membre_id
    famille.delete()
    return redirect("membre-view", id=idMbr)

def editFamily(request,id):
    user = request.user
    famille = get_object_or_404(Famille, id=id)
    membre = membre_pour(user, famille.membre_id, 'peut_modifier_famille')
    if request.method == 'POST':
        formulaire = FamilleForm(request.POST)
        if not formulaire.is_valid():
            message = erreurs_en_texte(formulaire)
            classe = 'alert alert-danger text-center'
            return rendre_formulaire(request, 'famille', locals(), status=400)
        donnees = formulaire.cleaned_data
        famille.user = user
        famille.membre=membre
        famille.beneficiere=donnees['nom']
        famille.qualite=donnees['qualite']
        famille.genre=donnees['genre']
        famille.annee=donnees['annee']
        famille.save()
        message = 'Mise à jour !'
        classe = 'alert alert-success text-center'
    return rendre_formulaire(request, 'famille', locals())

def editMoto(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    userMembre = Membre.objects.filter(id=user.membreId).first() if user.membreId else None
    villeId = userMembre.ville_id if userMembre else None
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    moto = engin_pour(user, id, 'peut_modifier_engin')
    membre = moto.proprietaire
    if request.method == 'POST':
        photo = request.FILES.get('photo')
        erreur_photo = erreur_image(photo) if photo else None
        if erreur_photo:
            message = erreur_photo
            classe = 'alert alert-danger text-center'
            return rendre_formulaire(request, 'moto', locals(), status=400)
        formulaire = EnginForm(request.POST)
        if not formulaire.is_valid():
            message = erreurs_en_texte(formulaire)
            classe = 'alert alert-danger text-center'
            return rendre_formulaire(request, 'moto', locals(), status=400)
        donnees = formulaire.cleaned_data
        moto.num_plaque = donnees['plaque']
        moto.num_chassie = donnees['chassie']
        moto.num_moteur = donnees['moteur']
        moto.marque = donnees['marque']
        moto.couleur = donnees['couleur']
        if photo:
            moto.photo = photo
        moto.save()
        message = "Mise à jour !"
        classe = 'alert alert-primary text-center'
        notify(user=moto.user, titre="Modification d'une moto", description=f"Numero:{moto.numero}")
    return rendre_formulaire(request, 'moto', locals())


#Redirection to membre-view
def viewUser(request, id):
    return redirect('membre-view', id=id)

#Vue de membreerrorPage
def membre_view(request, id):
    """Fiche d'un membre : lecture et actions « modifier », « envoyer » (demande de modification), « privilege ».

    404 si le membre est hors du périmètre du compte (voir compte.services.droits) ; 403 si l'action
    POST demandée est interdite ; 400 si le formulaire « modifier » est invalide (la fiche est réaffichée avec
    ``erreurs_modifier``). Contexte : membre, historique (lignes du journal, vide sans le droit), droits (dictionnaire) et
    chacune de ses clés à plat : voir `compte.services.droits.droits_membre`.
    """
    user = request.user
    membre, droits = membre_et_droits(user, id, supprimes_visibles=True)  # supprimé : visible de qui peut le restaurer

    erreurs_modifier = None
    message = None
    statut = 200
    if request.method == 'POST':
        if 'modifier' in request.POST:
            formulaire, modifie = modifier_membre(user, membre, request.POST, request.FILES)  # 403 sans droit
            if formulaire.errors:
                erreurs_modifier = formulaire.errors
                statut = 400
                membre = Membre.objects.get(pk=membre.pk)  # l'instance du formulaire porte des valeurs refusées
            elif modifie:
                notify(user=membre.user, membre=membre, titre=_("Modification d'un membre"))
        elif 'envoyer' in request.POST:
            resultat = demander_modification(user, membre, request.POST.get('demande'))  # 403 sans droit
            message = {'creee': _("Votre demande a été envoyée"), 'existante': _("Votre demande a déjà été envoyée"),
                       'vide': _("Indiquez votre demande.")}[resultat]
        elif 'privilege' in request.POST:
            # Réservé aux super-utilisateurs (403 sinon) : correctif minimal avant les rôles (sous-lot 2e).
            if not droits['peut_attribuer_privileges']:
                raise PermissionDenied
            compte = compte_du_membre(membre.id)
            if compte is not None:
                attribuer_privileges(user, compte, membre, request.POST)
    contexte = {
        'user': user, 'membre': membre, 'droits': droits, **droits,
        'erreurs_modifier': erreurs_modifier, 'message': message,
        **contexte_fiche(user, membre, droits),
    }
    return render(request, 'app/membre.html', contexte, status=statut)


#Vue de la moto
def moto_view(request, id):
    """Fiche d'un engin : visible si son propriétaire est dans le périmètre du compte (404 sinon)."""
    user = request.user
    moto = engin_pour(user, id)
    membre = moto.proprietaire
    membreUser = compte_du_membre(moto.proprietaire_id)
    verify = 1 if membreUser else 0
    motard = membres_du_perimetre(user).filter(id=moto.motard_id).first() if moto.motard_id else None
    return render(request, 'app/moto-view.html', locals())

#Vue de la liste des villes dans la province
def province_view(request, id):
    """Coordination provinciale et ses villes : lecture dans le périmètre du compte (404 sinon)."""
    user = request.user
    province = get_object_or_404(provinces_du_perimetre(user), id=id)
    villes = villes_du_perimetre(user).filter(province=province).order_by('nom')
    return render(request, 'app/province-view.html', locals())

#Recherche des membres ou de la moto
#Recherche des membres ou de la moto
def recherche(request):
    """Recherche de la barre du haut (POST) : membres et engins du PÉRIMÈTRE du compte, sans les supprimés.

    Les membres passent par le service de liste (nom, identifiant, téléphone) ; un engin est trouvé par son numéro
    si son propriétaire est visible du compte. Aucun résultat hors périmètre, même pour un visiteur.
    """
    user = request.user
    membres, motos = [], []
    if request.method == 'POST' and request.POST.get('search'):
        champ = (request.POST.get('champ') or '').strip()
        if champ:
            membres = list(membres_filtres(user, {'q': champ[:Q_LONGUEUR_MAX]})[:RESULTATS_MAX])
            motos = list(engins_visibles(user).filter(numero__icontains=champ[:Q_LONGUEUR_MAX]).select_related('proprietaire')[:RESULTATS_MAX])
        if not membres and not motos:
            membres = {}
            message = 'Aucun resultat !'
            classe = 'alert alert-danger text-center'
    return render(request, 'app/resultats.html', locals())

#Afficher la liste des antennes dans une ville
def ville_view(request, id):
    """Une ville (niveau hérité) et ses membres : lecture dans le périmètre du compte (404 sinon)."""
    user = request.user
    structure = AssociationMembre.objects.filter(users=user).first()
    userMembre = Membre.objects.filter(id=user.membreId).first() if user.membreId else None
    antennes = Antenne.objects.filter(structure=structure).order_by('nom')
    ville = get_object_or_404(villes_du_perimetre(user), id=id)
    membres = membres_du_perimetre(user).filter(ville=ville).order_by('nom', 'antenne')
    # les boutons « Ajout antenne » / « Ajout membre » visent une association membre de cette ville (jamais la ville elle-même)
    association_de_la_ville = associations_du_compte(user).filter(ville=ville).first()
    return render(request, 'app/ville-view.html', locals())

#Afficher la liste des membres
def membreListe(request):
    """Liste des membres (F-28) : recherche, filtres et pagination serveur (25 par page).

    Paramètres GET : ``q`` (nom, identifiant, téléphone), ``etat`` (saisi, valide_antenne, actif),
    ``qualite`` (MOTARD, PROPRIETAIRE, MOTARD ET PROPRIETAIRE), ``antenne`` (id), ``association`` (id), ``page``.

    Réponse : fragment ``coptapp/membres/partials/_liste.html`` pour une requête HTMX (hors navigation boostée),
    page complète ``app/membre-list.html`` sinon.

    Contexte fourni au gabarit :
    - ``page_obj`` : page courante (Page Django : itérable de Membre, ``paginator.count``, ``number``,
      ``start_index``, ``end_index``, ``has_previous`` / ``has_next``) ; une page illisible ou hors bornes ramène
      à la première ou à la dernière page ;
    - ``filtres`` : valeurs normalisées ``q``, ``etat``, ``qualite``, ``antenne``, ``association`` (chaînes ou
      entiers, vide si absent) pour préremplir le formulaire ;
    - ``filtres_actifs`` : vrai si une recherche ou un filtre est posé (message « aucun résultat » ou vide) ;
    - ``choix`` : ``antennes``, ``associations`` (du périmètre), ``qualites``, ``etats`` (codes) pour les listes
      déroulantes ;
    - les droits « en général » (``peut_creer_membre``, ``peut_valider``…, voir
      `compte.services.droits.droits_membre`) à plat, ``droits`` (le même dictionnaire) et ``user`` ;
    - sur chaque membre de ``page_obj`` : ``peut_valider`` (droit de valider CE membre, calculé sans requête).
    """
    user = request.user
    resultat = lister_membres(user, request.GET, request.GET.get('page'))
    droits = droits_membre(user)
    contexte = {
        'user': user,
        'page_obj': resultat.page_obj,
        'filtres': resultat.filtres,
        'filtres_actifs': resultat.filtres_actifs,
        'choix': choix_filtres(user),
        'nb_validables': compter_validables(user, resultat.filtres) if droits['peut_valider_tous'] else 0,  # modale « Valider tout le monde »
        'droits': droits,
        **droits,
    }
    modele = 'coptapp/membres/partials/_liste.html' if veut_fragment(request) else 'app/membre-list.html'
    return render(request, modele, contexte)


@require_GET
def enginListe(request):
    """Liste des engins (F-30) : GET seulement (405 sinon), dans le périmètre du compte (liste vide si rien n'est visible).

    Paramètres : ``q`` (numéro, plaque, châssis, moteur, propriétaire), ``coordination`` (id), ``antenne`` (id), ``page`` (25 par page).
    Fragment ``coptapp/engins/partials/_liste.html`` pour une requête HTMX, page complète ``coptapp/engins/liste.html`` sinon
    (gabarits à écrire par frontend-htmx). Contexte : ``page_obj``, ``filtres``, ``filtres_actifs``, ``choix`` (coordinations,
    antennes), ``droits`` et ``user``."""
    user = request.user
    resultat = lister_engins(user, request.GET, request.GET.get('page'))
    contexte = {'user': user, 'page_obj': resultat.page_obj, 'filtres': resultat.filtres, 'filtres_actifs': resultat.filtres_actifs,
                'choix': resultat.choix, 'droits': droits_membre(user)}
    modele = 'coptapp/engins/partials/_liste.html' if veut_fragment(request) else 'coptapp/engins/liste.html'
    return render(request, modele, contexte)


def notificationsView(request):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    userMembre = None
    if user.membreId:
        userMembre = Membre.objects.filter(id=user.membreId).first()
        if userMembre and userMembre.ville:
            villeId = userMembre.ville.id
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()

    # Un compte sans membre (ou dont le membre a disparu) reste valide : membre = None.
    membre = userMembre
    membreUser = compte_du_membre(user.membreId)
    verify = 1 if membreUser else 0

    notifys = myNotify(request)
    return render(request, 'app/notifications.html', locals())

def listMessage(request):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    userMembre = Membre.objects.filter(id=user.membreId).first() if user.membreId else None
    villeId = userMembre.ville_id if userMembre else None
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
    userMembre = Membre.objects.filter(id=user.membreId).first() if user.membreId else None
    villeId = userMembre.ville_id if userMembre else None
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    
    message = get_object_or_404(Communique, id=id)
    reactions = Reaction.objects.filter(communique=message)
    return render(request, 'app/message-view.html', locals())

@editeur_requis
def site(request):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    userMembre = Membre.objects.filter(id=user.membreId).first() if user.membreId else None
    villeId = userMembre.ville_id if userMembre else None
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()



    #Intitulé
    intit = "Ajouté l'article"

    #Add article
    if request.method == 'POST':
        titre = request.POST.get('titre')
        description = request.POST.get('description')
    
        if len(request.FILES) == 0:
            image = None
            message = "Echec de selection d'image"
            classe = 'alert alert-danger text-center'
        else:
            image = request.FILES.get('image')
            erreur_photo = erreur_image(image) if image else None
            if erreur_photo:
                image = None
                message = erreur_photo
                classe = 'alert alert-danger text-center'
                articles = Article.objects.order_by('-id')
                return rendre_formulaire(request, 'article', locals(), status=400, page='app/site.html')
            verify = Article.objects.filter(titre=titre).exists()

            if verify == False:
                galery = Galery.objects.create(image=image, principale=True)
                article = Article.objects.create(titre=titre,image=image,description=description)
                article.galery.add(galery)
                article.save()
                message = "Publication de l'article effectuée !"
                classe = 'alert alert-info text-center'
            else:
                message = "Cet article a déjà été publié"
                classe = 'alert alert-danger text-center'
        
    
    #Articles
    articles = Article.objects.order_by('-id')
    return rendre_formulaire(request, 'article', locals(), page='app/site.html')

@editeur_requis
def article(request, id):
    #Configuration
    messages = Communique.objects.order_by('-id')[0:3]
    user = request.user
    userMembre = Membre.objects.filter(id=user.membreId).first() if user.membreId else None
    villeId = userMembre.ville_id if userMembre else None
    notifications = myNotify(request)[0:3]
    antennes = Antenne.objects.order_by('nom')
    provinces = provinceSelector()
    
    
    #Intitulé
    intit = "Modifier l'article"
    
    #Article edit
    article = get_object_or_404(Article, id=id)
    if request.method == 'POST':
        image = request.FILES.get('image')
        erreur_photo = erreur_image(image) if image else None
        if erreur_photo:
            message = erreur_photo
            classe = 'alert alert-danger text-center'
            articles = Article.objects.order_by('-id')
            return rendre_formulaire(request, 'article', locals(), status=400, page='app/site.html')
        article.titre = request.POST.get('titre')
        article.description = request.POST.get('description')
        if image:  # un nouveau fichier valide seulement ; l'ancien est supprimé après validation de la transaction (signal)
            article.image = image
        message = "Mise à jour de l'article !"
        classe = 'alert alert-info text-center'
        article.save()
    
    #Articles
    articles = Article.objects.order_by('-id')
    return rendre_formulaire(request, 'article', locals(), page='app/site.html')

@editeur_requis
@require_POST
def deleteArticle(request, id):
    article = get_object_or_404(Article, id=id)
    article.delete()  # les fichiers sont supprimés par le signal post_delete, après validation de la transaction
    return redirect("site")