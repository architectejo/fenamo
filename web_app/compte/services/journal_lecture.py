"""Lecture du journal d'activités (F-71), réservée au super-utilisateur : filtres et pagination. Les valeurs « avant » et « après »
ne sont jamais renvoyées : seule l'existence du changement et son motif se lisent."""
from datetime import datetime, timedelta

from django.core.paginator import Paginator
from django.db.models import Q

from compte import roles
from compte.models import JournalAction

PAR_PAGE = 30


def _jour(texte):
    try:
        return datetime.strptime((texte or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def _entier(valeur):
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        return None
    return nombre if 0 < nombre <= 2**31 - 1 else None


def lister_journal(filtres, numero_page=None):
    """Page du journal, du plus récent au plus ancien. Filtres : q (auteur, objet, motif), action, role (code du rôle de l'auteur),
    coordination et antenne (identifiants du lieu de l'objet), du, au (AAAA-MM-JJ)."""
    lignes = JournalAction.objects.select_related('auteur').defer('avant', 'apres').order_by('-date', '-id')
    q = (filtres.get('q') or '').strip()[:100]
    if q:
        lignes = lignes.filter(Q(auteur__username__icontains=q) | Q(objet_libelle__icontains=q) | Q(motif__icontains=q))
    if filtres.get('role') in roles.ROLES:
        lignes = lignes.filter(role=filtres['role'])
    elif filtres.get('role') == 'herites':  # auteurs sans nomination : « privilèges P1,P3 » ou « utilisateur »
        lignes = lignes.filter(Q(role__startswith='privil') | Q(role='utilisateur'))
    for cle in ('coordination', 'antenne'):
        valeur = _entier(filtres.get(cle))
        if valeur:
            lignes = lignes.filter(**{f'{cle}_id': valeur})
    if filtres.get('action') in JournalAction.Action.values:
        lignes = lignes.filter(action=filtres['action'])
    du, au = _jour(filtres.get('du')), _jour(filtres.get('au'))
    if du:
        lignes = lignes.filter(date__date__gte=du)
    if au:
        lignes = lignes.filter(date__date__lt=au + timedelta(days=1))
    return Paginator(lignes, PAR_PAGE).get_page(numero_page)
