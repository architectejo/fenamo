"""Filtres et balises de gabarit du site : typographie française, nombres, dates, tailles, recherche."""
import re
from datetime import date, datetime

from django import template
from django.utils import timezone
from django.utils.html import conditional_escape, escape
from django.utils.safestring import mark_safe

register = template.Library()

NBSP = " "
ESPACE_FINE = " "
_BALISE = re.compile(r"(<[^>]*>)")
_NOM_BALISE = re.compile(r"^<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9]*)")
# Contenus laissés intacts : le texte d'un <option>, <title>, <textarea>, <script>, <style> ou <svg> n'accepte pas de balise
_BRUTS = frozenset({"script", "style", "textarea", "title", "option", "svg", "iframe"})
_AVANT_PONCTUATION = re.compile(r"[ \t\r\n]+([:;?!»])")
_APRES_GUILLEMET = re.compile(r"(«)[ \t\r\n]+")
SIGLE = "FENAMO-RDC"
_SIGLE_ENVELOPPE = '<bdi class="insecable">FENAMO-RDC</bdi>'


def typographie(html: str) -> str:
    """Typographie française appliquée au texte d'un fragment HTML (jamais aux balises ni aux attributs).

    - espace insécable avant « : ; ? ! » et à l'intérieur des guillemets « » ;
    - « FENAMO-RDC » entouré de <span class="insecable"> : jamais coupé au trait d'union.
    """
    sortie, brut, precedent = [], None, ""
    for morceau in _BALISE.split(html):
        if morceau.startswith("<") and morceau.endswith(">"):
            m = _NOM_BALISE.match(morceau)
            if m:
                nom = m.group(2).lower()
                if brut is None and not m.group(1) and nom in _BRUTS and not morceau.endswith("/>"):
                    brut = nom
                elif brut == nom and m.group(1):
                    brut = None
            sortie.append(morceau)
            precedent = morceau
            continue
        if brut is None and morceau:
            morceau = _AVANT_PONCTUATION.sub(NBSP + r"\1", morceau)
            morceau = _APRES_GUILLEMET.sub(r"\1" + NBSP, morceau)
            if SIGLE in morceau and 'class="insecable"' not in precedent:
                morceau = morceau.replace(SIGLE, _SIGLE_ENVELOPPE)
        sortie.append(morceau)
        if morceau:
            precedent = morceau
    return "".join(sortie)


@register.filter(name="typo", is_safe=True, needs_autoescape=True)
def typo_filtre(valeur, autoescape=True):
    """Typographie française d'un texte (par exemple venu de l'API) ; le texte est échappé d'abord."""
    texte = conditional_escape(valeur) if autoescape else valeur
    return mark_safe(typographie(str(texte)))


class _TypoNoeud(template.Node):
    def __init__(self, nodelist):
        self.nodelist = nodelist

    def render(self, context):
        return mark_safe(typographie(self.nodelist.render(context)))


@register.tag(name="typo")
def typo_bloc(parser, token):
    """{% typo %}…{% endtypo %} : typographie française du HTML déjà rendu du bloc."""
    nodelist = parser.parse(("endtypo",))
    parser.delete_first_token()
    return _TypoNoeud(nodelist)


@register.filter
def nombre(valeur):
    """54182 -> « 54 182 » (espace fine insécable)."""
    if valeur is None or valeur == "":
        return ""
    try:
        return f"{int(valeur):,}".replace(",", ESPACE_FINE)
    except (TypeError, ValueError):
        return str(valeur)


@register.filter
def date_fr(valeur):
    """JJ/MM/AAAA, en heure de Kinshasa pour un instant."""
    if isinstance(valeur, datetime):
        if timezone.is_aware(valeur):
            valeur = timezone.localtime(valeur)
        return valeur.strftime("%d/%m/%Y")
    if isinstance(valeur, date):
        return valeur.strftime("%d/%m/%Y")
    return ""


@register.filter
def date_iso(valeur):
    if isinstance(valeur, datetime):
        if timezone.is_aware(valeur):
            valeur = timezone.localtime(valeur)
        return valeur.date().isoformat()
    if isinstance(valeur, date):
        return valeur.isoformat()
    return ""


@register.filter
def heure_fr(valeur):
    """« 08 h 40 » (espaces insécables)."""
    if isinstance(valeur, datetime):
        if timezone.is_aware(valeur):
            valeur = timezone.localtime(valeur)
        return f"{valeur:%H}{NBSP}h{NBSP}{valeur:%M}"
    return ""


@register.filter
def taille_fr(octets):
    """Taille de fichier lisible : 14 -> « 14 o », 245760 -> « 240 Ko », 3,4 Mo (virgule, espace insécable)."""
    if not isinstance(octets, int) or octets < 0:
        return ""
    if octets < 1024:
        return f"{octets}{NBSP}o"
    for diviseur, unite in ((1024**3, "Go"), (1024**2, "Mo"), (1024, "Ko")):
        if octets >= diviseur:
            valeur = octets / diviseur
            texte = f"{valeur:.0f}" if valeur >= 100 or unite == "Ko" else f"{valeur:.1f}".replace(".", ",")
            return texte.replace(".0", "") + NBSP + unite
    return ""


@register.filter
def surligner(texte, mot):
    """Entoure d'un <mark> les occurrences de `mot` dans `texte` (texte échappé d'abord, insensible à la casse)."""
    echappe = str(conditional_escape(texte))
    mot = (mot or "").strip()
    if len(mot) < 2:
        return mark_safe(echappe)
    motif = re.compile("(" + re.escape(str(escape(mot))) + ")", re.IGNORECASE)
    return mark_safe(motif.sub(r"<mark>\1</mark>", echappe))


@register.simple_tag
def icone(nom, variante=""):
    """Icône du sprite local (`static/img/icons.svg`), décorative : {% icone "globe" %} ou {% icone "check" "petite" %}."""
    from django.templatetags.static import static

    classe = "ic" + (f" ic--{variante}" if variante else "")
    return mark_safe(
        f'<svg class="{escape(classe)}" aria-hidden="true" focusable="false"><use href="{escape(static("img/icons.svg"))}#i-{escape(nom)}"></use></svg>'
    )


@register.filter
def tel(numero):
    """+243 812 345 678 -> +243812345678 (pour href="tel:")."""
    return re.sub(r"[^\d+]", "", str(numero or ""))


@register.simple_tag(takes_context=True)
def lien_page(context, numero):
    """Adresse de la page `numero` de la liste en cours, en gardant les autres paramètres (type, q…)."""
    from urllib.parse import urlencode

    requete = context.get("request")
    params = [(k, v) for k, v in requete.GET.items() if k != "page"] if requete else []
    if numero > 1:
        params.append(("page", numero))
    return "?" + urlencode(params) if params else requete.path if requete else "?"


@register.simple_tag
def pages_visibles(page, pages):
    """Numéros à montrer : première, dernière et voisines de la page courante, None pour « … »."""
    voulus = sorted({1, pages, page - 1, page, page + 1} & set(range(1, pages + 1)))
    resultat, precedent = [], 0
    for n in voulus:
        if n - precedent > 1:
            resultat.append(None)
        resultat.append(n)
        precedent = n
    return resultat
