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

from coptapp.services.etats import LIBELLES, etat_de
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
    try:
        url = photo.url if photo else ''
    except ValueError:  # champ image sans fichier associé
        url = ''
    variante = ' avatar--grand' if int(taille) >= 64 else (' avatar--petit' if int(taille) <= 32 else '')
    if classe:
        variante += ' ' + classe
    if url:
        return format_html('<span class="avatar{}"><img src="{}" alt="" loading="lazy" width="{}" height="{}"></span>', variante, url, taille, taille)
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


# Noms envoyés par la modale « Modifier » -> champs du modèle (voir coptapp.services.membres.ALIAS_POST).
ALIAS_MODIFIER = {'about': 'a_propos', 'date': 'date_naissance', 'autre_asbl': 'autre_asb', 'epouse': 'nom_epouse'}


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


@register.filter
def motif_a_reprendre(membre):
    """Motif proposé à la suppression : celui de la demande en cours ; jamais celui d'une ancienne suppression restaurée."""
    if getattr(membre, 'suppression_demandee', False) and not getattr(membre, 'is_delete', False):
        return membre.motif_suppression
    return ''
