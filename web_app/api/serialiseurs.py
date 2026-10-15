"""Sérialiseurs du site public : chaque réponse est construite champ par champ (liste blanche explicite, jamais ``__all__``).

Ne sont jamais exposés : identifiants internes, auteur, ``is_delete``, brouillons, ``integration_code``, chemins disque, données de
compte ou de membre, clés. Les fichiers sortent en adresses absolues bâties sur ``PUBLIC_MEDIA_BASE_URL`` (stockage public seulement)."""
import logging
import re
from urllib.parse import quote, urlsplit

from django.conf import settings
from django.utils import timezone

from coptapp.validators import nom_vignette
from virtrine.services.html_propre import nettoyer_html

logger = logging.getLogger('api.site')
LANGUES = ('fr', 'ln', 'sw', 'lua', 'kg')
_YOUTUBE = re.compile(r'^[A-Za-z0-9_-]{6,20}$')


# ---------------------------------------------------------------- dates et fichiers

def date_heure(valeur):
    """ISO 8601 avec fuseau (heure de Kinshasa) ; None si vide."""
    if not valeur:
        return None
    if timezone.is_naive(valeur):
        valeur = timezone.make_aware(valeur)
    return timezone.localtime(valeur).isoformat()


def date_seule(valeur):
    """Date calendaire ISO 8601 (AAAA-MM-JJ) ; None si vide."""
    return valeur.isoformat() if valeur else None


def _base_media(request):
    base = getattr(settings, 'PUBLIC_MEDIA_BASE_URL', '')
    return base if base else request.build_absolute_uri(settings.MEDIA_URL)


def url_fichier(request, nom):
    """Adresse absolue d'un fichier du stockage public ; None si le nom est vide ou suspect (jamais de chemin hors média)."""
    if not nom or nom.startswith('/') or '..' in nom.split('/') or '\\' in nom:
        return None
    base = _base_media(request)
    return base + ('' if base.endswith('/') else '/') + quote(nom)


def taille_fichier(fichier):
    try:
        return fichier.size
    except (OSError, ValueError):
        return None


def image(request, fichier, vignette_stockee=None):
    """{url, vignette, largeur, hauteur} ou None. La vignette est le fichier voisin ``…_vignette`` s'il existe, sinon l'image elle-même."""
    if not fichier or not fichier.name:
        return None
    url = url_fichier(request, fichier.name)
    if url is None:
        return None
    vignette = vignette_stockee or nom_vignette(fichier.name)
    try:
        if not fichier.storage.exists(vignette):
            vignette = fichier.name
        largeur, hauteur = fichier.width, fichier.height
    except (OSError, ValueError):
        logger.warning("Image illisible dans le stockage public : %s", fichier.name)
        vignette, largeur, hauteur = fichier.name, None, None
    return {'url': url, 'vignette': url_fichier(request, vignette), 'largeur': largeur, 'hauteur': hauteur}


def lien_web(valeur):
    """Lien http(s) seulement (jamais javascript: ni data:) ; None sinon."""
    valeur = (valeur or '').strip()
    morceaux = urlsplit(valeur)
    return valeur if morceaux.scheme in ('http', 'https') and morceaux.netloc else None


# ---------------------------------------------------------------- vidéo

def video(lien):
    """{fournisseur, identifiant} d'un lien YouTube ou Facebook, sinon None. Facebook : l'identifiant est l'adresse https complète
    (Facebook n'a pas d'identifiant court). Aucun code d'intégration n'existe côté API : le site fabrique le lecteur."""
    if not lien:
        return None
    morceaux = urlsplit(lien)
    hote = (morceaux.hostname or '').lower()
    if morceaux.scheme != 'https':
        return None
    if hote == 'youtu.be':
        identifiant = morceaux.path.strip('/').split('/')[0]
    elif hote == 'youtube.com' or hote.endswith('.youtube.com'):
        chemin = [p for p in morceaux.path.split('/') if p]
        if chemin[:1] in (['embed'], ['shorts'], ['live']) and len(chemin) > 1:
            identifiant = chemin[1]
        else:
            valeurs = dict(p.split('=', 1) for p in morceaux.query.split('&') if '=' in p)
            identifiant = valeurs.get('v', '')
    elif hote in ('facebook.com', 'www.facebook.com', 'm.facebook.com', 'fb.watch'):
        return {'fournisseur': 'facebook', 'identifiant': lien}
    else:
        return None
    return {'fournisseur': 'youtube', 'identifiant': identifiant} if _YOUTUBE.match(identifiant) else None


# ---------------------------------------------------------------- articles

def _contenu(article, langue):
    """(langue effective, traduction ou None) : repli sur le français si la traduction manque. Les traductions sont préchargées."""
    if langue != 'fr':
        for traduction in article.traductions.all():
            if traduction.langue == langue and traduction.titre:
                return langue, traduction
    return 'fr', None


def article_liste(request, article, langue):
    effective, trad = _contenu(article, langue)
    return {
        'slug': article.slug,
        'type': article.type,
        'titre': trad.titre if trad else (article.titre or ''),
        'resume': trad.resume if trad else article.resume,
        'image': image(request, article.image),
        'date_publication': date_heure(article.date_publication),
        'langue': effective,
        'traduit': effective == langue,
    }


def article_detail(request, article, langue, langues_actives, galerie):
    """`article.traductions` est préchargé avec TOUTES les traductions (le choix de la langue se fait ici)."""
    donnees = article_liste(request, article, langue)
    _effective, trad = _contenu(article, langue)
    donnees['texte'] = nettoyer_html(trad.texte if trad else article.description)  # nettoyé à l'enregistrement ET à la sortie
    donnees['video'] = video(article.lien_video)
    donnees['galerie'] = [element_galerie(request, g, None) for g in galerie]
    traduites = {t.langue for t in article.traductions.all() if t.titre}
    donnees['langues_disponibles'] = ['fr'] + [c for c in LANGUES[1:] if c in langues_actives and c in traduites]
    donnees['mise_a_jour'] = date_heure(article.mise_a_jour)
    return donnees


def element_galerie(request, g, slug_article):
    est_video = g.type == 'video'
    return {
        'type': g.type,
        'image': None if est_video else image(request, g.image, g.vignette.name if g.vignette else None),
        'video': video(g.lien_video) if est_video else None,
        'legende': g.legende,
        'date': date_seule(g.date),
        'article': slug_article,
    }


# ---------------------------------------------------------------- config, comité, géographie, statistiques

def config(request, cfg, telephones, partenaires, documents, derniere_maj):
    application = None
    if cfg.apk and cfg.apk.name and cfg.apk_version:
        application = {'version': cfg.apk_version, 'url': url_fichier(request, cfg.apk.name), 'taille': taille_fichier(cfg.apk),
                       'date': date_seule(cfg.apk_date), 'notice': cfg.apk_notice}
    return {
        'nom': 'FENAMO-RDC',
        'nom_complet': cfg.nom or 'Fédération Nationale des Associations des Motocyclistes Taximen de la RDC',
        'devise': cfg.slogant or 'Unité, Discipline et Progrès',
        'message_accueil': cfg.welcome_text or '',
        'logo': image(request, cfg.logo),
        'image_fond': image(request, cfg.image_background),
        'siege': cfg.adresse or '',
        'email': cfg.gmail or None,
        'telephones': [{'libelle': t.libelle, 'numero': t.numero} for t in telephones],
        'reseaux': {'facebook': lien_web(cfg.facebook), 'x': lien_web(cfg.twitter), 'youtube': lien_web(cfg.youtube),
                    'instagram': lien_web(cfg.instagram), 'linkedin': lien_web(cfg.linkedin)},
        'partenaires': [{'nom': p.nom, 'lien': lien_web(p.lien), 'logo': image(request, p.logo)} for p in partenaires],
        'langues_actives': cfg.langues(),
        'paiement_en_ligne': bool(cfg.paiement_en_ligne_actif),
        'documents': [{'titre': d.titre, 'type': d.type, 'url': url_fichier(request, d.fichier.name), 'taille': taille_fichier(d.fichier),
                       'date': date_seule(d.date)} for d in documents],
        'application': application,
        'mise_a_jour': date_heure(derniere_maj),
    }


def comite(request, membres):
    return {
        'mandat': {'debut': None, 'fin': None},  # pas encore saisi dans F-63 (le modèle n'a pas de dates de mandat)
        'membres': [{'nom': m.nom, 'fonction': m.fonction, 'fonction_code': m.fonction_code, 'photo': image(request, m.photo),
                     'ordre': m.ordre} for m in membres],
    }


def coordination(c, antennes):
    return {'code': c.code, 'nom': c.nom, 'ordre': c.ordre,
            'antennes': [{'code': a.code, 'nom': a.nom, 'type': a.type or None} for a in antennes]}


def statistiques(calcul, maintenant):
    nat = calcul['national']
    return {
        'date_calcul': date_heure(maintenant),
        'membres_actifs': nat['membres_actifs'],
        'engins_actifs': None,  # masqués tant que leurs états ne sont pas faits (F-30, F-32)
        'engins_par_type': None,
        'associations_membres': nat['associations'],
        'coordinations': nat['coordinations'],
        'par_coordination': [{'code': ligne['code'], 'nom': ligne['nom'], 'membres_actifs': ligne['membres_actifs'],
                              'associations_membres': ligne['associations'], 'antennes': ligne['antennes'], 'engins_actifs': None}
                             for ligne in calcul['coordinations']],
    }
