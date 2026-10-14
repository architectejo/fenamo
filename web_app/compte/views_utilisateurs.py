"""Écran « Utilisateurs » (F-02, F-03, F-05, F-06) : liste des comptes gérables, mandats à traiter, nomination, compte externe,
mot de passe temporaire, désactivation, réactivation, changement de rôle, renouvellement.

Règles :
- les vues sont minces : toute la règle métier est dans ``compte.services.nominations`` (portée, anti-escalade, journal) ;
- un compte inconnu ou hors périmètre répond 404, un droit insuffisant 403, une règle métier refusée est une erreur de formulaire
  (statut 422, la modale reste ouverte avec la saisie) ;
- toute modification passe par POST (jeton CSRF) ; personne n'agit sur son propre compte ;
- le mot de passe temporaire n'existe que dans la réponse au POST (``Cache-Control: no-store``, ``hx-history="false"``) : jamais
  dans un message, une session, un en-tête, le journal ni un second affichage.
"""
import json
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods

from compte import roles
from compte.models import Nomination
from compte.services import nominations as noms
from compte.services.comptes import en_groupes
from compte.services.droits import antennes_du_perimetre, associations_du_compte, membres_du_perimetre, provinces_du_perimetre
from coptapp.models import Antenne, AssociationMembre, Membre, Province
from coptapp.services.etats import etat_de
from fenamo.htmx import reponse_succes, veut_fragment

Compte = get_user_model()
PAR_PAGE = 25
MOTIF_MAX = 500
EVENEMENT = 'utilisateursModifies'
ETATS_COMPTE_PUCES = ('actif', 'temporaire', 'desactive')
ROLES_DE_GESTION = (roles.SU, roles.PR, roles.VN, roles.VP, roles.VA)


# ---------------------------------------------------------------- accès

def _auteur_autorise(request):
    """L'écran est réservé à qui peut nommer au moins un rôle (SU, PR, VN, VP, VA) ; sinon 403."""
    if not noms.roles_nommables(request.user):
        raise PermissionDenied
    return request.user


def _compte_a_gerer(auteur, id):
    """Compte visé par une action : 404 s'il n'existe pas ou n'est pas dans le périmètre, 403 si le droit manque (dont soi-même)."""
    compte = Compte.objects.filter(pk=id).first()
    if compte is None:
        raise Http404
    try:
        noms._verifier_gestion(auteur, compte)  # même règle que les services (une seule source)
    except noms.HorsPerimetre:
        raise Http404
    except noms.DroitInsuffisant:
        raise PermissionDenied
    return compte


def _nomination_de(compte):
    return Nomination.objects.filter(compte=compte, active=True).select_related('coordination', 'antenne', 'association', 'nomme_par').first()


# ---------------------------------------------------------------- présentation (textes, jauges)

def _duree_en_toutes_lettres(jours):
    if jours < 60:
        return _("%(n)s jour") % {'n': jours} if jours == 1 else _("%(n)s jours") % {'n': jours}
    mois_total = jours // 30
    ans, mois = divmod(mois_total, 12)
    if ans == 0:
        return _("%(n)s mois") % {'n': mois}
    texte = _("%(n)s an") % {'n': ans} if ans == 1 else _("%(n)s ans") % {'n': ans}
    if mois:
        texte += ' ' + _("et %(n)s mois") % {'n': mois}
    return texte


def lieu_de(nomination):
    """« National », « Coordination Haut-Katanga », « Antenne de Lemba · ALEMO asbl »."""
    if nomination is None:
        return ''
    if nomination.antenne_id:
        texte = _("Antenne de %(nom)s") % {'nom': nomination.antenne.nom}
        if nomination.antenne.coordination_id and nomination.association_id is None:
            return texte
        if nomination.association_id:
            texte += ' · ' + (nomination.association.sigle or nomination.association.nom or '')
        return texte
    if nomination.coordination_id:
        return _("Coordination %(nom)s") % {'nom': nomination.coordination.nom}
    if nomination.role in (roles.PR, roles.VN, roles.SU) or nomination.role == roles.VI:
        return _("National")
    return ''


def mandat_de(nomination, aujourdhui=None):
    """Dictionnaire pour components/_mandat.html : variante, fin, reste, part (palier de 5 appliqué par le gabarit)."""
    jour = aujourdhui or timezone.localdate()
    if nomination is None:
        return {'variante': 'sans', 'fin': _("Aucun mandat"), 'reste': '', 'part': 0}
    if nomination.fin is None:
        reste = _("accès en lecture seule") if nomination.role == roles.VI else _("sans limite de durée")
        return {'variante': 'sans', 'fin': _("Sans date de fin"), 'reste': reste, 'part': 0}
    etat = noms.etat_mandat(nomination, jour)
    ecart = (nomination.fin - jour).days
    if etat == 'echu':
        reste = _("échu depuis %(d)s") % {'d': _duree_en_toutes_lettres(-ecart)}
        variante = 'echu'
    else:
        reste = _("dans %(d)s") % {'d': _duree_en_toutes_lettres(ecart)}
        variante = 'bientot' if etat == 'a_echoir' else 'cours'
    total = max((nomination.fin - nomination.debut).days, 1)
    part = max(0, min(100, round(100 * (jour - nomination.debut).days / total)))
    return {'variante': variante, 'fin': nomination.fin.strftime('%d/%m/%Y'), 'reste': reste, 'part': part}


def etat_du_compte(compte):
    if not compte.is_active:
        return 'desactive'
    return 'mdp_temporaire' if compte.doit_changer_mot_de_passe else 'actif'


def _ligne(auteur, compte, nomination=None, aujourdhui=None):
    if nomination is None:
        liste = getattr(compte, 'nomination_active_liste', None)
        nomination = liste[0] if liste else None
    soi = compte.pk == auteur.pk
    membre = Membre.objects.filter(pk=compte.membreId).only('nom', 'idf').first() if compte.membreId else None
    nom = (membre.nom if membre and membre.nom else '') or compte.get_full_name() or compte.username
    if nomination is not None and nomination.nomme_par_id:
        par = _("vous") if nomination.nomme_par_id == auteur.pk else (nomination.nomme_par.get_full_name() or nomination.nomme_par.username)
        nomme_par = _("nommé par %(nom)s") % {'nom': par}
    else:
        nomme_par = ''
    peut = False if soi else noms.peut_gerer(auteur, compte)
    super_utilisateur = nomination is None and compte.is_superuser
    return {
        'compte': compte, 'nom': nom, 'membre': membre, 'externe': not compte.membreId and not compte.is_superuser, 'soi': soi,
        'nomination': nomination or ({'role': 'SU'} if super_utilisateur else None),
        'role': nomination.role if nomination else ('SU' if super_utilisateur else ''),
        'role_libelle': nomination.get_role_display() if nomination else (str(roles.LIBELLES[roles.SU]) if super_utilisateur else ''),
        'lieu': lieu_de(nomination) if nomination else (_("National") if super_utilisateur else ''), 'nomme_par': nomme_par,
        'mandat': mandat_de(nomination, aujourdhui) if nomination or not super_utilisateur else
        {'variante': 'sans', 'fin': _("Sans date de fin"), 'reste': _("compte technique"), 'part': 0}, 'etat': etat_du_compte(compte),
        'peut_gerer': peut, 'peut_renouveler': bool(peut and nomination and roles.duree_par_defaut(nomination.role)),
    }


def _filtres(request):
    p = request.GET
    return {cle: (p.get(cle) or '').strip() for cle in ('q', 'role', 'coordination', 'antenne', 'mandat', 'etat')}


def _entier(valeur):
    """Entier positif tenant dans une clé primaire (2**31 - 1) ; None sinon (pas d'OverflowError sur un identifiant géant)."""
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        return None
    return nombre if 0 < nombre <= 2147483647 else None


def _filtres_pour_service(filtres):
    sortie = dict(filtres)
    for cle in ('coordination', 'antenne'):
        sortie[cle] = _entier(sortie.get(cle)) or ''
    if sortie.get('etat') not in ETATS_COMPTE_PUCES:
        sortie['etat'] = ''
    if sortie.get('mandat') not in noms.ETATS_MANDAT:
        sortie['mandat'] = ''
    if sortie.get('role') and sortie['role'].upper() not in (*roles.ROLES, 'SANS'):
        sortie['role'] = ''
    return sortie


def _choix_perimetre(auteur):
    return {
        'coordinations': provinces_du_perimetre(auteur).order_by('ordre', 'nom'),
        'antennes': antennes_du_perimetre(auteur).exclude(nom=None).order_by('nom'),
        'associations': associations_du_compte(auteur).order_by('sigle', 'nom'),
    }


# ---------------------------------------------------------------- liste et mandats

def _contexte_comptes(request, auteur):
    filtres = _filtres_pour_service(_filtres(request))
    page = Paginator(noms.lister_comptes_gerables(auteur, filtres), PAR_PAGE).get_page(request.GET.get('page'))
    lignes = [_ligne(auteur, c) for c in page]
    if page.number == 1 and not any(filtres.values()):  # sa propre ligne, sans action : « Votre compte »
        lignes.insert(0, _ligne(auteur, auteur, _nomination_de(auteur)))
    nb_filtres = sum(1 for cle in ('role', 'coordination', 'antenne', 'mandat') if filtres.get(cle))
    return {
        'page_obj': page, 'lignes': lignes, 'filtres': filtres, 'filtres_actifs': any(filtres.values()), 'nb_filtres': nb_filtres,
        'puces': (('', _("Tous")), ('actif', _("Actifs")), ('temporaire', _("Mot de passe temporaire")), ('desactive', _("Désactivés"))),
        'mandat_options': (('', _("Tous")), ('cours', None), ('a_echoir', _("Fin dans les 60 jours")), ('echu', _("Échu")),
                           ('sans_fin', _("Sans date de fin"))),
    }


def _contexte_mandats(auteur):
    jour = timezone.localdate()
    tous = list(noms.mandats_a_traiter(auteur))
    echus = [n for n in tous if noms.etat_mandat(n, jour) == 'echu']
    bientot = [n for n in tous if noms.etat_mandat(n, jour) == 'a_echoir']
    gerables = noms.comptes_gerables(auteur)
    actives = Nomination.objects.filter(active=True, compte__in=gerables)
    return {
        'echus': [_ligne(auteur, n.compte, n, jour) for n in echus],
        'bientot': [_ligne(auteur, n.compte, n, jour) for n in bientot],
        'nb_echus': len(echus), 'nb_bientot': len(bientot),
        'nb_en_cours': actives.filter(fin__gt=jour + timedelta(days=noms.JOURS_ALERTE)).count(),
        'nb_sans_fin': actives.filter(fin__isnull=True).count(),
    }


@require_GET
def utilisateurs(request):
    """Page complète, ou zone seule (``zone=comptes`` / ``zone=mandats``) pour une requête HTMX."""
    auteur = _auteur_autorise(request)
    zone = request.GET.get('zone')
    if veut_fragment(request) and zone == 'mandats':
        return render(request, 'compte/utilisateurs/partials/_mandats.html', _contexte_mandats(auteur))
    contexte = _contexte_comptes(request, auteur)
    if veut_fragment(request):
        return render(request, 'compte/utilisateurs/partials/_zone_comptes.html', contexte)
    contexte.update(_contexte_mandats(auteur))
    contexte.update(_choix_perimetre(auteur))
    contexte.update({
        'onglet': 'mandats' if request.GET.get('onglet') == 'mandats' else 'comptes',
        'total_comptes': noms.comptes_gerables(auteur).count(),
        'roles_filtre': [(code, roles.LIBELLES[code]) for code in (roles.PR, roles.VN, roles.VP, roles.VA, roles.AT, roles.VI, roles.ED)],
        'peut_externe': auteur.is_superuser or noms._role_de(auteur) == roles.PR,
        'perimetre_libelle': _libelle_perimetre(auteur),
    })
    return render(request, 'compte/utilisateurs/utilisateurs.html', contexte)


def _libelle_perimetre(auteur):
    from compte.services.droits import profil_de
    profil = profil_de(auteur)
    nomination = getattr(profil, 'nomination', None)
    if profil.mode == 'su' or nomination is None:
        return _("National")
    return lieu_de(nomination)


# ---------------------------------------------------------------- recherche d'un membre à nommer

def _raison_non_nommable(membre, avec_nomination):
    if membre.pk in avec_nomination:
        return _("Déjà nommé : %(role)s.") % {'role': str(roles.LIBELLES.get(avec_nomination[membre.pk], '')).lower()}
    if not membre.is_validate3:
        return _("Pas encore actif : la validation nationale manque.")
    return _("Ce membre ne peut pas être nommé.")


@require_GET
def membres_nommables(request):
    """Fragment des résultats de recherche (components/_choix_membre.html) : les membres du périmètre qui correspondent, les non
    nommables restant visibles avec leur raison."""
    auteur = _auteur_autorise(request)
    q = (request.GET.get('q') or '').strip()[:100]
    resultats = []
    if q:
        trouves = (membres_du_perimetre(auteur).filter(is_delete=False)
                   .filter(nom__icontains=q) | membres_du_perimetre(auteur).filter(is_delete=False, numero_carte_de_membre__icontains=q)
                   | membres_du_perimetre(auteur).filter(is_delete=False, telephone__icontains=q)).select_related('antenne').distinct()[:8]
        nommables = set(noms.membres_nommables(auteur).values_list('pk', flat=True))
        avec_nomination = {}
        for n in Nomination.objects.filter(active=True, compte__membreId__in=[m.pk for m in trouves]).select_related('compte'):
            avec_nomination[n.compte.membreId] = n.role
        for m in trouves:
            resultats.append({
                'id': m.pk, 'nom': m.nom or '—', 'identifiant': m.numero_carte_de_membre or m.idf or f'MBR{m.pk:07d}',
                'lieu': _("Antenne de %(nom)s") % {'nom': m.antenne.nom} if m.antenne_id else '—', 'etat': etat_de(m),
                'nommable': m.pk in nommables, 'raison': '' if m.pk in nommables else _raison_non_nommable(m, avec_nomination),
            })
    return render(request, 'compte/utilisateurs/partials/_resultats_membres.html', {'resultats': resultats, 'q': q})


# ---------------------------------------------------------------- aides pour les formulaires POST

def _date(valeur):
    valeur = (valeur or '').strip()
    if not valeur:
        return None
    for format_ in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(valeur, format_).date()
        except ValueError:
            continue
    raise noms.RegleMetier(_("Date invalide : écrivez JJ/MM/AAAA."))


def _perimetre(post):
    """(coordination, antenne, association) lus dans le POST ; identifiant inconnu = règle métier refusée."""
    sortie = []
    for champ, modele in (('coordination', Province), ('antenne', Antenne), ('association', AssociationMembre)):
        identifiant = _entier(post.get(champ))
        if not identifiant:
            sortie.append(None)
            continue
        objet = modele.objects.filter(pk=identifiant).first()
        if objet is None:
            raise noms.RegleMetier(_("Périmètre inconnu."))
        sortie.append(objet)
    return tuple(sortie)


def _mdp_reponse(request, compte, mot_de_passe, titre, evenements=True):
    """Modale du mot de passe temporaire : lecture unique, jamais en cache ni en historique."""
    reponse = render(request, 'compte/utilisateurs/partials/_modale_mdp.html', {
        'titre': titre, 'compte': compte, 'valeur': mot_de_passe, 'groupes': en_groupes(mot_de_passe).split(' '),
    })
    add_never_cache_headers(reponse)
    reponse['Cache-Control'] = 'no-store, private'
    if evenements:
        reponse['HX-Trigger'] = '{"%s": true}' % EVENEMENT
    return reponse


def _erreur_formulaire(request, modele, contexte, erreur):
    return render(request, modele, {**contexte, 'erreur': str(erreur)}, status=422)


def _roles_choisissables(auteur):
    return [(code, roles.LIBELLES[code], _sous_titre_role(code)) for code in noms.roles_nommables(auteur)]


def _sous_titre_role(code):
    duree = roles.duree_par_defaut(code)
    niveau = roles.PERIMETRE_DU_ROLE.get(code)
    lieu = {roles.NATIONAL: _("National"), roles.COORDINATION: _("Une coordination"), roles.ANTENNE: _("Une antenne")}.get(niveau, '')
    if duree:
        return _("%(lieu)s · mandat de %(n)s ans") % {'lieu': lieu, 'n': duree}
    return lieu or (_("Lecture seule") if code == roles.VI else _("Contenu du site"))


# ---------------------------------------------------------------- nommer un membre (F-02)

@require_http_methods(['GET', 'POST'])
def nommer(request):
    auteur = _auteur_autorise(request)
    contexte = {
        'action': request.path, 'roles_choix': _roles_choisissables(auteur), **_choix_perimetre(auteur),
        'durees_json': json.dumps({code: roles.duree_par_defaut(code) for code in roles.ROLES if roles.duree_par_defaut(code)}), 'aujourdhui': timezone.localdate(),
    }
    if request.method == 'GET':
        membre = None
        identifiant = _entier(request.GET.get('membre'))
        if identifiant:
            membre = membres_du_perimetre(auteur).filter(pk=identifiant).first()
            if membre is None:
                raise Http404
        contexte['membre_retenu'] = membre
        contexte['debut_texte'] = timezone.localdate().strftime('%d/%m/%Y')
        return render(request, 'compte/utilisateurs/partials/_modale_nommer.html', contexte)
    identifiant = _entier(request.POST.get('membre'))
    role = request.POST.get('role', '')
    membre = membres_du_perimetre(auteur).filter(pk=identifiant).first() if identifiant else None
    contexte['membre_retenu'] = membre
    contexte['saisie'] = request.POST
    contexte['debut_texte'] = request.POST.get('debut') or timezone.localdate().strftime('%d/%m/%Y')
    if membre is None:
        if identifiant:
            raise Http404
        return _erreur_formulaire(request, 'compte/utilisateurs/partials/_modale_nommer.html', contexte, _("Choisissez un membre."))
    try:
        coordination, antenne, association = _perimetre(request.POST)
        nomination, mot_de_passe = noms.nommer(auteur, membre, role, coordination=coordination, antenne=antenne, association=association,
                                               debut=_date(request.POST.get('debut')), fin=_date(request.POST.get('fin')))
    except noms.HorsPerimetre:
        raise Http404
    except noms.DroitInsuffisant:
        raise PermissionDenied
    except noms.RegleMetier as erreur:
        return _erreur_formulaire(request, 'compte/utilisateurs/partials/_modale_nommer.html', contexte, erreur)
    if mot_de_passe:
        return _mdp_reponse(request, nomination.compte, mot_de_passe, _("Membre nommé"))
    return reponse_succes(_("Membre nommé"), evenements=[EVENEMENT])


# ---------------------------------------------------------------- compte externe (F-03)

@require_http_methods(['GET', 'POST'])
def ajouter_externe(request):
    auteur = _auteur_autorise(request)
    if not (auteur.is_superuser or noms._role_de(auteur) == roles.PR):
        raise PermissionDenied
    contexte = {'action': request.path, 'peut_editeur': auteur.is_superuser, **_choix_perimetre(auteur)}
    if request.method == 'GET':
        return render(request, 'compte/utilisateurs/partials/_modale_externe.html', contexte)
    contexte['saisie'] = request.POST
    type_ = request.POST.get('type', roles.VI)
    portee = request.POST.get('portee', 'national')
    try:
        coordination, antenne, _asso = _perimetre({'coordination': request.POST.get('coordination') if portee == 'coordination' else '',
                                                   'antenne': request.POST.get('antenne') if portee == 'antenne' else ''})
        if type_ == roles.VI and portee == 'coordination' and coordination is None:
            raise noms.RegleMetier(_("Choisissez une coordination."))
        if type_ == roles.VI and portee == 'antenne' and antenne is None:
            raise noms.RegleMetier(_("Choisissez une antenne."))
        compte, nomination, mot_de_passe = noms.creer_compte_externe(
            auteur, request.POST.get('username'), type_, email=(request.POST.get('email') or '').strip(),
            coordination=coordination if type_ == roles.VI else None, antenne=antenne if type_ == roles.VI else None)
    except noms.HorsPerimetre:
        raise Http404
    except noms.DroitInsuffisant:
        raise PermissionDenied
    except noms.RegleMetier as erreur:
        return _erreur_formulaire(request, 'compte/utilisateurs/partials/_modale_externe.html', contexte, erreur)
    return _mdp_reponse(request, compte, mot_de_passe, _("Compte créé"))


# ---------------------------------------------------------------- actions sur un compte

@require_http_methods(['GET', 'POST'])
def reinitialiser(request, id):
    auteur = _auteur_autorise(request)
    compte = _compte_a_gerer(auteur, id)
    contexte = {'action': request.path, 'compte': compte, 'cible': _ligne(auteur, compte)}
    if request.method == 'GET':
        return render(request, 'compte/utilisateurs/partials/_modale_reinitialiser.html', contexte)
    try:
        mot_de_passe = noms.reinitialiser_mot_de_passe(auteur, compte)
    except noms.HorsPerimetre:
        raise Http404
    except noms.DroitInsuffisant:
        raise PermissionDenied
    except noms.RegleMetier as erreur:
        return _erreur_formulaire(request, 'compte/utilisateurs/partials/_modale_reinitialiser.html', contexte, erreur)
    return _mdp_reponse(request, compte, mot_de_passe, _("Mot de passe réinitialisé"))


@require_http_methods(['GET', 'POST'])
def desactiver(request, id):
    auteur = _auteur_autorise(request)
    compte = _compte_a_gerer(auteur, id)
    contexte = {'action': request.path, 'compte': compte, 'cible': _ligne(auteur, compte), 'motif_max': MOTIF_MAX,
                'suggestions': (_("Départ de la fédération"), _("Mandat terminé"), _("Compte en double"), _("Demande de l'intéressé"))}
    if request.method == 'GET':
        return render(request, 'compte/utilisateurs/partials/_modale_desactiver.html', contexte)
    motif = (request.POST.get('motif') or '').strip()
    contexte['motif'] = motif
    if not motif:
        return _erreur_formulaire(request, 'compte/utilisateurs/partials/_modale_desactiver.html', {**contexte, 'erreur_motif': True},
                                  _("Indiquez le motif de la désactivation."))
    if len(motif) > MOTIF_MAX:
        return _erreur_formulaire(request, 'compte/utilisateurs/partials/_modale_desactiver.html', contexte,
                                  _("Le motif est limité à 500 caractères."))
    try:
        noms.desactiver(auteur, compte, motif)
    except noms.HorsPerimetre:
        raise Http404
    except noms.DroitInsuffisant:
        raise PermissionDenied
    return reponse_succes(_("Compte désactivé"), evenements=[EVENEMENT])


@require_http_methods(['GET', 'POST'])
def reactiver(request, id):
    auteur = _auteur_autorise(request)
    compte = _compte_a_gerer(auteur, id)
    contexte = {'action': request.path, 'compte': compte, 'cible': _ligne(auteur, compte)}
    if request.method == 'GET':
        return render(request, 'compte/utilisateurs/partials/_modale_reactiver.html', contexte)
    try:
        noms.reactiver(auteur, compte)
        if request.POST.get('nouveau_mdp'):  # décision par défaut : pas de mot de passe temporaire sans que la case soit cochée
            return _mdp_reponse(request, compte, noms.reinitialiser_mot_de_passe(auteur, compte), _("Compte réactivé"))
    except noms.HorsPerimetre:
        raise Http404
    except noms.DroitInsuffisant:
        raise PermissionDenied
    return reponse_succes(_("Compte réactivé"), evenements=[EVENEMENT])


@require_http_methods(['GET', 'POST'])
def changer_role(request, id):
    auteur = _auteur_autorise(request)
    compte = _compte_a_gerer(auteur, id)
    ligne = _ligne(auteur, compte)
    contexte = {'action': request.path, 'compte': compte, 'cible': ligne, 'roles_choix': _roles_choisissables(auteur),
                **_choix_perimetre(auteur), 'durees': {code: roles.duree_par_defaut(code) for code in roles.ROLES}}
    if request.method == 'GET':
        return render(request, 'compte/utilisateurs/partials/_modale_changer.html', contexte)
    contexte['saisie'] = request.POST
    try:
        coordination, antenne, association = _perimetre(request.POST)
        noms.changer_role_perimetre(auteur, compte, request.POST.get('role', ''), coordination=coordination, antenne=antenne,
                                    association=association, motif=(request.POST.get('motif') or '').strip()[:MOTIF_MAX],
                                    fin=_date(request.POST.get('fin')))
    except noms.HorsPerimetre:
        raise Http404
    except noms.DroitInsuffisant:
        raise PermissionDenied
    except noms.RegleMetier as erreur:
        return _erreur_formulaire(request, 'compte/utilisateurs/partials/_modale_changer.html', contexte, erreur)
    return reponse_succes(_("Changement enregistré"), evenements=[EVENEMENT])


@require_http_methods(['GET', 'POST'])
def renouveler(request, id):
    auteur = _auteur_autorise(request)
    compte = _compte_a_gerer(auteur, id)
    ligne = _ligne(auteur, compte)
    nomination = ligne['nomination']
    duree = roles.duree_par_defaut(nomination.role) if nomination else None
    contexte = {'action': request.path, 'compte': compte, 'cible': ligne, 'duree': duree,
                'nouvelle_fin': (timezone.localdate() + timedelta(days=365 * duree)) if duree else None}
    if request.method == 'GET':
        return render(request, 'compte/utilisateurs/partials/_modale_renouveler.html', contexte)
    try:
        noms.renouveler_mandat(auteur, compte, (request.POST.get('motif') or '').strip()[:MOTIF_MAX])
    except noms.HorsPerimetre:
        raise Http404
    except noms.DroitInsuffisant:
        raise PermissionDenied
    except noms.RegleMetier as erreur:
        return _erreur_formulaire(request, 'compte/utilisateurs/partials/_modale_renouveler.html', contexte, erreur)
    return reponse_succes(_("Mandat renouvelé"), evenements=[EVENEMENT])
