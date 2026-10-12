"""Balises de gabarit du système de design (docs/design/systeme-de-design.md).

Chargement : ``{% load design %}`` (bibliothèque déclarée dans TEMPLATES['OPTIONS']['libraries']).

- ``{% icone "users" %}``                 : icône du sprite static/img/icons.svg (Lucide, licence ISC).
- ``{% badge_etat "actif" %}``             : badge d'état du circuit de validation (components/_badge_etat.html).
- ``{{ membre|etat_membre }}``             : code d'état déduit des booléens hérités (provisoire, voir ci-dessous).
- ``{% avatar nom photo 48 %}``            : photo ou initiales (avatar neutre).
- ``{% indicateurs_tableau_bord as ind %}`` : chiffres du tableau de bord (provisoire, voir ci-dessous).
"""
from django import template
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from coptapp.services.etats import etat_de
from coptapp.services.historique import historique_objet as _historique
from coptapp.services.tableau_bord import indicateurs_tableau_bord as _indicateurs

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


@register.filter
def libelle_etat(code):
    return ETATS.get(code, code)


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


@register.simple_tag(takes_context=True)
def indicateurs_tableau_bord(context):
    """Chiffres du tableau de bord pour l'utilisateur de la requête (calculés par coptapp.services.tableau_bord)."""
    return _indicateurs(context['request'].user)


@register.simple_tag
def historique_objet(objet, limite=15):
    """Dernières lignes du journal d'activités concernant un objet (coptapp.services.historique)."""
    return _historique(objet, limite)


@register.filter
def part_du_max(valeur, valeurs):
    """Largeur (0 à 100) d'une barre de répartition par rapport à la plus grande valeur de la série."""
    try:
        maximum = max(valeurs)
        return round(100 * valeur / maximum) if maximum else 0
    except (TypeError, ValueError):
        return 0


@register.simple_tag(takes_context=True)
def paginer(context, objets, par_page=25):
    """Page courante (paramètre ``page`` de l'adresse) d'une liste fournie par une vue héritée qui ne pagine pas.

    PROVISOIRE : la pagination et la recherche passeront par le serveur dans la vue (F-28) ; cette balise évite
    d'envoyer des milliers de lignes au téléphone en attendant.
    """
    from django.core.paginator import Paginator
    return Paginator(objets, par_page).get_page(context['request'].GET.get('page'))
