"""Gestion du contenu du site public (F-60 à F-66) : règles testables appelées par les écrans et l'API ; tout changement est journalisé (F-70).

Droits : éditeur (ED) ou super-utilisateur pour les articles, la galerie, la configuration, les documents, le comité, les partenaires et les
téléphones (``PermissionDenied`` sinon) ; SUPER-UTILISATEUR seul pour l'activation des langues (F-64) et du paiement en ligne (F-65).
Chaque écriture passe par une liste blanche de champs, valide le modèle (``full_clean``), écrit en transaction, journalise (auteur, avant /
après pour les valeurs courtes, noms des champs pour les autres) puis demande la purge du cache du site APRÈS le commit.
Les textes d'article sont nettoyés (liste blanche de balises) à l'enregistrement par le modèle ; ``integration_code`` n'est jamais écrit ici.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from compte.models import JournalAction
from compte.services.droits import est_editeur
from compte.services.journal import journaliser
from virtrine.models import (
    LANGUES_SITE, Article, ArticleTraduction, Config, DocumentPublic, Galery, MembreComite, Partenaire, TelephoneSite,
)
from virtrine.services.purge import demander_purge

CHAMPS_MODIFIABLES = {
    Article: ('titre', 'description', 'resume', 'type', 'lien_video', 'image'),
    ArticleTraduction: ('langue', 'titre', 'resume', 'texte'),
    Galery: ('type', 'legende', 'lien_video', 'date', 'ordre', 'publie', 'image'),
    MembreComite: ('nom', 'fonction', 'fonction_code', 'ordre', 'photo'),
    DocumentPublic: ('titre', 'type', 'date', 'fichier'),
    Partenaire: ('nom', 'lien', 'ordre', 'logo'),
    TelephoneSite: ('numero', 'libelle', 'ordre'),
    Config: ('nom', 'slogant', 'welcome_text', 'description', 'adresse', 'facebook', 'twitter', 'youtube', 'gmail', 'instagram', 'linkedin',
             'logo', 'image_background', 'apk', 'apk_version', 'apk_date', 'apk_notice'),
}
# Valeurs courtes sans donnée sensible : conservées avant / après au journal ; pour les autres champs seul le NOM est gardé.
VALEURS_JOURNALISEES = frozenset({'type', 'statut', 'ordre', 'publie', 'langue', 'fonction_code', 'apk_version', 'apk_date', 'date',
                                  'langues_actives', 'paiement_en_ligne_actif', 'titre', 'nom', 'fonction'})


def _exiger_editeur(auteur):
    if not est_editeur(auteur):
        raise PermissionDenied


def _exiger_super_utilisateur(auteur):
    if not (auteur.is_authenticated and auteur.is_active and auteur.is_superuser):
        raise PermissionDenied


def _valeur(objet, champ):
    valeur = getattr(objet, champ)
    return str(valeur) if hasattr(valeur, 'name') and not isinstance(valeur, (str, int, bool)) else valeur


def _journaliser(auteur, objet, avant, apres, modifies, creation, motif=''):
    visibles = [c for c in modifies if c in VALEURS_JOURNALISEES]
    journaliser(auteur, JournalAction.Action.MODIFICATION, objet,
                avant={c: avant.get(c) for c in visibles},
                apres={**{c: apres.get(c) for c in visibles}, 'champs_modifies': modifies, **({'creation': True} if creation else {})},
                motif=motif, libelle=str(objet)[:200])


@transaction.atomic
def enregistrer(auteur, objet, donnees, fichiers=None):
    """Crée ou modifie un contenu du site. `donnees` : champs texte ; `fichiers` : champs fichier (images, PDF, APK). Seuls les champs de
    la liste blanche de ce modèle sont acceptés (ValueError sinon, c'est une erreur de programmation). ValidationError si le contenu est
    invalide (rien n'est écrit). Retourne l'objet enregistré."""
    _exiger_editeur(auteur)
    blanche = CHAMPS_MODIFIABLES[type(objet)]
    champs = {**(donnees or {}), **(fichiers or {})}
    inconnus = set(champs) - set(blanche)
    if inconnus:
        raise ValueError(f'Champs non modifiables : {sorted(inconnus)}')
    creation = objet.pk is None
    avant = {c: _valeur(objet, c) for c in blanche} if not creation else {}
    modifies = []
    for nom, valeur in champs.items():
        if creation or getattr(objet, nom) != valeur or nom in (fichiers or {}):
            setattr(objet, nom, valeur)
            modifies.append(nom)
    if not modifies and not creation:
        return objet
    objet.full_clean(exclude=[c.name for c in objet._meta.concrete_fields if c.name not in blanche and c.name != 'slug'])
    objet.save()
    apres = {c: _valeur(objet, c) for c in blanche}
    _journaliser(auteur, objet, avant, apres, modifies, creation)
    demander_purge()
    return objet


@transaction.atomic
def supprimer(auteur, objet):
    """Supprime un contenu (définitif : les contenus du site n'ont pas de suppression logique). Journalisé, puis purge."""
    _exiger_editeur(auteur)
    if type(objet) not in CHAMPS_MODIFIABLES or isinstance(objet, Config):
        raise ValueError('Ce contenu ne se supprime pas.')
    libelle = str(objet)[:200]
    identifiant = objet.pk
    journaliser(auteur, JournalAction.Action.SUPPRESSION, objet, avant={'type': getattr(objet, 'type', '')}, apres={'supprime': True},
                motif=_('Suppression définitive de contenu du site'), libelle=libelle)
    objet.delete()
    demander_purge()
    return identifiant


@transaction.atomic
def publier_article(auteur, article):
    """Publie un article (F-60) : titre en français obligatoire, date de publication posée à la première publication, journalisé, purge."""
    _exiger_editeur(auteur)
    article = Article.objects.select_for_update().get(pk=article.pk)
    if not (article.titre or '').strip():
        raise ValidationError(_("Le titre en français est obligatoire pour publier."))
    avant = {'statut': article.statut}
    if article.statut != Article.Statut.PUBLIE:
        article.statut = Article.Statut.PUBLIE
        article.date_publication = article.date_publication or timezone.now()
        article.save(update_fields=['statut', 'date_publication', 'mise_a_jour'])
        _journaliser(auteur, article, avant, {'statut': article.statut}, ['statut'], False, motif=_('Publication'))
        demander_purge()
    return article


@transaction.atomic
def depublier_article(auteur, article, motif=''):
    """Repasse un article en brouillon (il disparaît du site) ; journalisé avec le motif, purge."""
    _exiger_editeur(auteur)
    article = Article.objects.select_for_update().get(pk=article.pk)
    avant = {'statut': article.statut}
    if article.statut != Article.Statut.BROUILLON:
        article.statut = Article.Statut.BROUILLON
        article.save(update_fields=['statut', 'mise_a_jour'])
        _journaliser(auteur, article, avant, {'statut': article.statut}, ['statut'], False, motif=motif or _('Retrait de la publication'))
        demander_purge()
    return article


@transaction.atomic
def enregistrer_traduction(auteur, article, langue, titre, resume='', texte=''):
    """Crée ou remplace la traduction de `article` dans `langue` (ln, sw, lua, kg) ; le français est l'article lui-même."""
    if langue not in dict(LANGUES_SITE):
        raise ValidationError(_("Langue inconnue."))
    traduction = ArticleTraduction.objects.filter(article=article, langue=langue).first() or ArticleTraduction(article=article, langue=langue)
    return enregistrer(auteur, traduction, {'titre': titre, 'resume': resume, 'texte': texte})


@transaction.atomic
def definir_langues_actives(auteur, langues):
    """F-64 : active les langues nationales données (le français est toujours actif). SUPER-UTILISATEUR seul ; journalisé ; purge."""
    _exiger_super_utilisateur(auteur)
    valides = [code for code, _nom in LANGUES_SITE]
    demandees = [c for c in valides if c in set(langues or [])]
    config = Config.instance()
    avant = {'langues_actives': config.langues_actives}
    nouvelle = ','.join(['fr'] + demandees)
    if nouvelle != config.langues_actives:
        config.langues_actives = nouvelle
        config.save(update_fields=['langues_actives'])
        _journaliser(auteur, config, avant, {'langues_actives': nouvelle}, ['langues_actives'], False)
        demander_purge()
    return config


@transaction.atomic
def definir_paiement_en_ligne(auteur, actif):
    """F-65 : interrupteur unique du paiement en ligne (désactivé par défaut). SUPER-UTILISATEUR seul ; changement journalisé ; purge."""
    _exiger_super_utilisateur(auteur)
    config = Config.instance()
    actif = bool(actif)
    if config.paiement_en_ligne_actif != actif:
        avant = {'paiement_en_ligne_actif': config.paiement_en_ligne_actif}
        config.paiement_en_ligne_actif = actif
        config.save(update_fields=['paiement_en_ligne_actif'])
        _journaliser(auteur, config, avant, {'paiement_en_ligne_actif': actif}, ['paiement_en_ligne_actif'], False)
        demander_purge()
    return config


def televerser_apk(auteur, fichier, version, notice=''):
    """Téléverse l'APK de l'application mobile (validé : ZIP avec AndroidManifest.xml, taille réglable) avec sa version et sa notice ;
    la date est celle du jour. Journalisé (noms des champs, version), purge."""
    return enregistrer(auteur, Config.instance(), {'apk_version': (version or '').strip()[:30], 'apk_notice': notice, 'apk_date': timezone.localdate()},
                       {'apk': fichier})
