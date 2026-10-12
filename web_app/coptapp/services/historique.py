"""Historique d'un objet : dernières lignes du journal d'activités (F-70)."""
from django.contrib.contenttypes.models import ContentType

from compte.models import JournalAction


def historique_objet(objet, limite=15):
    """Dernières lignes du journal concernant `objet` (action, auteur, date, motif).

    PROVISOIRE : lecture seule, sans contrôle de droits, en attendant l'écran du journal (F-71).
    Les valeurs « avant » et « après » ne sont jamais affichées par les gabarits ; l'appelant ne doit pas les exposer.
    """
    if objet is None or not getattr(objet, 'pk', None):
        return []
    return list(
        JournalAction.objects.filter(
            objet_type=ContentType.objects.get_for_model(objet, for_concrete_model=False), objet_id=objet.pk,
        ).select_related('auteur').order_by('-date', '-id')[:limite]
    )
