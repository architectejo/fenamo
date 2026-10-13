"""Adresses des pièces et photos privées : ``{% load fichiers %}`` puis ``{% url_fichier membre "photo" %}``.

Renvoie l'adresse de la vue contrôlée (jamais /media/) ou une chaîne vide si le champ n'a pas de fichier.
``vignette=True`` demande la vignette de 160 px d'une photo : ``{% url_fichier membre "photo" vignette=True %}``.
"""
from django import template
from django.urls import reverse

from coptapp.models import AssociationMembre, Membre

register = template.Library()


@register.simple_tag
def url_fichier(objet, champ, vignette=False):
    if objet is None or not getattr(objet, champ, None):
        return ''
    type_objet = 'membre' if isinstance(objet, Membre) else 'association' if isinstance(objet, AssociationMembre) else None
    if type_objet is None:
        return ''
    adresse = reverse('fichier', kwargs={'type_objet': type_objet, 'id': objet.pk, 'champ': champ})
    return adresse + ('?vignette=1' if vignette else '')
