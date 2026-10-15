"""Nettoyage du HTML des textes d'article (site public, § 10.1 : « aucun contenu HTML libre n'est injecté tel quel »).

Liste blanche, appliquée à l'ENREGISTREMENT : p, br, strong, em, ul, ol, li, h2, h3, a[href] (http et https seulement). Tout le reste est
retiré en gardant le texte ; script et style disparaissent avec leur contenu ; les attributs sont tous supprimés sauf ``href`` d'un lien
valide (``rel="noopener noreferrer"`` ajouté). Aucune bibliothèque externe (nh3 et bleach ne sont pas dans requirements.txt) : analyse par
``html.parser`` de la bibliothèque standard, texte ré-échappé, balises refermées.
"""
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit

BALISES = frozenset({'p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'h2', 'h3', 'a'})
VIDES = frozenset({'br'})
EFFACER_AVEC_CONTENU = frozenset({'script', 'style', 'iframe', 'object', 'embed', 'template', 'noscript', 'svg', 'math'})
PROFONDEUR_MAX = 30


def lien_autorise(adresse):
    """Vrai pour une adresse http(s) absolue ; refuse javascript:, data:, vbscript:, //hote sans schéma, etc."""
    nettoye = ''.join(c for c in (adresse or '') if c >= ' ' and c != '\x7f').strip()
    try:
        morceaux = urlsplit(nettoye)
    except ValueError:
        return False
    return morceaux.scheme.lower() in ('http', 'https') and bool(morceaux.netloc) and len(nettoye) <= 2000


class _Nettoyeur(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sortie = []
        self.ouvertes = []
        self.ignore = 0  # profondeur dans un élément effacé avec son contenu

    def handle_starttag(self, balise, attributs):
        if balise in EFFACER_AVEC_CONTENU:
            self.ignore += 1
            return
        if self.ignore or balise not in BALISES:
            return
        if balise == 'a':
            href = dict(attributs).get('href') or ''
            if not lien_autorise(href) or len(self.ouvertes) >= PROFONDEUR_MAX:
                return  # le lien est retiré, son texte reste
            self.sortie.append(f'<a href="{escape(href.strip(), quote=True)}" rel="noopener noreferrer">')
            self.ouvertes.append('a')
            return
        if balise in VIDES:
            self.sortie.append('<br>')
            return
        if len(self.ouvertes) >= PROFONDEUR_MAX:
            return
        self.sortie.append(f'<{balise}>')
        self.ouvertes.append(balise)

    def handle_startendtag(self, balise, attributs):
        self.handle_starttag(balise, attributs)
        if balise not in VIDES and balise in BALISES and balise != 'a':
            self.handle_endtag(balise)

    def handle_endtag(self, balise):
        if balise in EFFACER_AVEC_CONTENU:
            self.ignore = max(self.ignore - 1, 0)
            return
        if self.ignore or balise not in BALISES or balise in VIDES or balise not in self.ouvertes:
            return
        while self.ouvertes:  # referme jusqu'à la balise visée (imbrication cassée réparée)
            haut = self.ouvertes.pop()
            self.sortie.append(f'</{haut}>')
            if haut == balise:
                break

    def handle_data(self, donnees):
        if not self.ignore:
            self.sortie.append(escape(donnees, quote=False))

    def handle_comment(self, donnees):
        return  # commentaires et déclarations : supprimés

    def resultat(self):
        while self.ouvertes:
            self.sortie.append(f'</{self.ouvertes.pop()}>')
        return ''.join(self.sortie)


def nettoyer_html(texte):
    """HTML réduit à la liste blanche ; chaîne vide pour une valeur vide."""
    if not texte:
        return ''
    nettoyeur = _Nettoyeur()
    nettoyeur.feed(str(texte))
    nettoyeur.close()
    return nettoyeur.resultat().strip()
