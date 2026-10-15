"""Balises de gabarit du système de design (docs/design/systeme-de-design.md).

Chargement : ``{% load design %}`` (bibliothèque déclarée dans TEMPLATES['OPTIONS']['libraries']).

- ``{% icone "users" %}``                 : icône du sprite static/img/icons.svg (Lucide, licence ISC).
- ``{% badge_etat "actif" %}``             : badge d'état du circuit de validation (components/_badge_etat.html).
- ``{{ membre|etat_membre }}``             : code d'état déduit des booléens hérités (provisoire, voir ci-dessous).
- ``{% avatar nom photo 48 %}``            : photo ou initiales (avatar neutre).
"""
import math

from django import template
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from coptapp.forms import ALIAS_POST
from coptapp.templatetags.fichiers import url_fichier
from coptapp.services.etats import ETATS, LIBELLES, etat_de
from fenamo.htmx import veut_fragment as _veut_fragment

register = template.Library()


@register.simple_tag
def icone(nom, classe=''):
    """Icône SVG du sprite. Décorative (aria-hidden) : le texte voisin porte le sens."""
    return format_html(
        '<svg class="ic {}" aria-hidden="true" focusable="false"><use href="{}#i-{}"></use></svg>',
        classe, static('img/icons.svg'), nom,
    )


@register.filter
def etat_membre(objet):
    """Code d'état (snake_case : saisi, valide_antenne, actif…) d'un membre ou d'un engin, lu par le service etat_de."""
    return etat_de(objet)

# Qualités enregistrées en majuscules par l'écran hérité : libellés affichés en casse de phrase.
QUALITES = {
    'PROPRIETAIRE': _('Propriétaire'),
    'MOTARD': _('Motard'),
    'MOTARD ET PROPRIETAIRE': _('Motard et propriétaire'),
}


@register.filter
def libelle_qualite(valeur):
    """Libellé d'une qualité (« Motard et propriétaire ») ; « — » si elle est vide ou « ... » (non précisée)."""
    if not valeur or valeur == '...':
        return '—'
    return QUALITES.get(valeur, valeur)


@register.inclusion_tag('components/_badge_etat.html')
def badge_etat(code, change=False):
    """Badge d'état du circuit : rend le composant components/_badge_etat.html (libellé + pastilles, jamais la couleur seule)."""
    return {'etat': code, 'change': change}


@register.filter
def initiales(nom):
    mots = [m for m in str(nom or '').replace('-', ' ').split() if m]
    if not mots:
        return '?'
    if len(mots) == 1:
        return mots[0][:2].upper()
    return (mots[0][0] + mots[1][0]).upper()


@register.simple_tag
def avatar(nom, photo=None, taille=40, classe=''):
    """Avatar neutre (la couleur est réservée aux états) : photo si elle existe, sinon initiales.

    ``taille`` choisit la variante CSS : 64 et plus = ``avatar--grand``, 32 et moins = ``avatar--petit``.
    """
    url = ''
    if photo:
        # La photo d'un membre est privée : adresse de la vue contrôlée (vignette de 160 px), jamais /media/.
        url = url_fichier(getattr(photo, 'instance', None), getattr(getattr(photo, 'field', None), 'name', 'photo'), vignette=True)
    variante = ' avatar--grand' if int(taille) >= 64 else (' avatar--petit' if int(taille) <= 32 else '')
    if classe:
        variante += ' ' + classe
    if url:
        return format_html('<span class="avatar{}"><img src="{}" alt="" loading="lazy" decoding="async" width="{}" height="{}"></span>', variante, url, taille, taille)
    return format_html('<span class="avatar{}" aria-hidden="true">{}</span>', variante, initiales(nom))


@register.filter
def part_du_max(valeur, valeurs):
    """Largeur (0 à 100) d'une barre de répartition par rapport à la plus grande valeur de la série."""
    try:
        maximum = max(valeurs)
        return round(100 * valeur / maximum) if maximum else 0
    except (TypeError, ValueError):
        return 0


@register.filter
def palier_5(valeur):
    """Arrondit une part (0 à 100) au palier de 5 supérieur (une part non nulle reste visible) : classe ``part-N`` de app.css."""
    try:
        valeur = float(valeur)
    except (TypeError, ValueError):
        return 0
    return min(100, math.ceil(valeur / 5) * 5) if valeur > 0 else 0


@register.filter
def libelle_code_etat(code):
    """Libellé d'un code d'état du service (``valide_antenne``) : « Validé antenne »."""
    return LIBELLES.get(code, code)


@register.filter
def veut_fragment(request):
    """Vrai si la requête attend un fragment (voir fenamo.htmx.veut_fragment) : sert à n'émettre les zones hors bande qu'alors."""
    return _veut_fragment(request)


# Noms envoyés par la modale « Modifier » -> champs du modèle : table UNIQUE définie dans coptapp.forms (ALIAS_POST).
ALIAS_MODIFIER = ALIAS_POST


def _saisie_refusee(context):
    """Vrai si la fiche est réaffichée après un formulaire « Modifier » invalide : la saisie de l'utilisateur est conservée."""
    requete = context.get('request')
    return bool(context.get('erreurs_modifier')) and requete is not None and 'modifier' in requete.POST


@register.simple_tag(takes_context=True)
def saisie(context, nom, defaut=''):
    """Valeur d'un champ de la modale « Modifier » : la saisie refusée si le formulaire est invalide, sinon la valeur actuelle."""
    if _saisie_refusee(context):
        return context['request'].POST.get(nom, '')
    return '' if defaut is None else defaut


@register.simple_tag(takes_context=True)
def selectionne(context, nom, defaut, option):
    """`` selected`` si `option` est la valeur à afficher (saisie refusée ou valeur actuelle) dans une liste de la modale « Modifier »."""
    return ' selected' if str(saisie(context, nom, defaut)) == str(option) else ''


@register.simple_tag(takes_context=True)
def erreur_modifier(context, nom):
    """Message d'erreur d'un champ de la modale « Modifier » (sous le champ, lié par aria-describedby)."""
    erreurs = context.get('erreurs_modifier') or {}
    messages = erreurs.get(ALIAS_MODIFIER.get(nom, nom))
    if not messages:
        return ''
    return format_html(
        '<p class="champ-erreur" id="mm-{}-erreur"><svg class="ic" aria-hidden="true" focusable="false"><use href="{}#i-circle-alert"></use></svg>{}</p>',
        nom, static('img/icons.svg'), ' '.join(messages),
    )


@register.simple_tag(takes_context=True)
def invalide(context, nom):
    """Attributs ARIA d'un champ refusé de la modale « Modifier »."""
    erreurs = context.get('erreurs_modifier') or {}
    if erreurs.get(ALIAS_MODIFIER.get(nom, nom)):
        return format_html(' aria-invalid="true" aria-describedby="mm-{}-erreur"', nom)
    return ''


# Libellés au pluriel des puces de filtre (« Saisis », « Actifs »…) : mêmes codes que coptapp.services.etats.ETATS.
LIBELLES_PLURIELS = {
    'saisi': _('Saisis'),
    'valide_antenne': _('Validés antenne'),
    'valide_province': _('Validés province'),
    'actif': _('Actifs'),
    'renvoye': _('Renvoyés'),
    'a_renouveler': _('À renouveler'),
    'supprime': _('Supprimés'),
}
assert set(LIBELLES_PLURIELS) == set(ETATS), 'LIBELLES_PLURIELS doit couvrir exactement les codes de coptapp.services.etats.ETATS'


@register.filter
def libelle_pluriel_etat(code):
    """Libellé d'un code d'état au pluriel (puces de filtre) ; à défaut, le libellé au singulier de la table unique."""
    return LIBELLES_PLURIELS.get(code) or LIBELLES.get(code, code)


@register.filter
def peut_nommer(droits):
    """Vrai si le contexte de droits de la coque (fn_droits) permet de nommer des utilisateurs : clé ``peut_nommer`` de ``droits_menu``, déduite de compte.roles.NOMMABLES."""
    return bool(droits) and bool(droits.get('peut_nommer'))


@register.filter
def niveau_alerte(classe):
    """Niveau du composant d'alerte pour une classe de message héritée (alert-success, alert-info… = « succes », sinon « danger »)."""
    from coptapp.views.modales import niveau_message
    return niveau_message(classe)


@register.filter
def heure_fr(valeur):
    """Heure locale au format « 07 h 40 » (espaces insécables) : ``{{ etat.depuis|heure_fr }}``. Vide si la valeur est vide."""
    if not valeur:
        return ''
    from django.utils import timezone
    if timezone.is_aware(valeur):
        valeur = timezone.localtime(valeur)
    return format_html('{}&nbsp;h&nbsp;{}', valeur.strftime('%H'), valeur.strftime('%M'))
