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

from coptapp.services.etats import etat_de
from fenamo.htmx import veut_fragment as _veut_fragment

register = template.Library()

# Circuit de validation (CLAUDE.md « Règles métier ») : saisi -> validé antenne -> validé province -> actif,
# plus « renvoyé », « à renouveler » et « supprimé ».
ETATS = {
    'saisi': _('Saisi'),
    'valide-antenne': _('Validé antenne'),
    'valide-province': _('Validé province'),
    'actif': _('Actif'),
    'renvoye': _('Renvoyé'),
    'a-renouveler': _('À renouveler'),
    'supprime': _('Supprimé'),
}


@register.simple_tag
def icone(nom, classe=''):
    """Icône SVG du sprite. Décorative (aria-hidden) : le texte voisin porte le sens."""
    return format_html(
        '<svg class="ic {}" aria-hidden="true" focusable="false"><use href="{}#i-{}"></use></svg>',
        classe, static('img/icons.svg'), nom,
    )


@register.filter
def etat_membre(objet):
    """Code d'état (forme des classes CSS, avec tirets) d'un membre ou d'un engin, lu par le service etat_de."""
    return etat_de(objet).replace('_', '-')

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
    return ETATS.get(str(code).replace('_', '-'), code)


@register.filter
def veut_fragment(request):
    """Vrai si la requête attend un fragment (voir fenamo.htmx.veut_fragment) : sert à n'émettre les zones hors bande qu'alors."""
    return _veut_fragment(request)
