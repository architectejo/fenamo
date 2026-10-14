"""Reprise des données : état unique du membre (§ 4.4), à partir des anciens booléens.

Correspondance (voir docs/correspondance-etat-membre.md), dans cet ordre, par lots :
  1. tout le monde            -> saisi
  2. is_validate2             -> valide_antenne
  3. is_validate3             -> actif (y compris is_validate3 sans is_validate2 : cas ambigu, listé par
                                 ``manage.py verifier_etats_membres``)
  4. renvoye                  -> renvoye, avec etat_precedent = état calculé aux étapes 1 à 3
  5. is_delete                -> etat_precedent = etat, PUIS etat = supprime (DEUX mises à jour : MySQL évalue les
                                 affectations de gauche à droite)

ORM seulement, modèles historiques, ``queryset.update`` (aucun save()). Les fonctions sont recopiées ici : la
migration ne dépend pas du code de l'application. Les booléens ne sont jamais modifiés dans le sens direct.
Rejouable : chaque étape ne retient que les lignes encore non converties (un état déjà posé n'est pas dégradé).
Sens inverse : les booléens sont recalculés depuis l'état.
"""
from django.db import migrations

LOT = 500
ETATS = ('saisi', 'valide_antenne', 'valide_province', 'actif', 'renvoye', 'a_renouveler', 'supprime')


def miroirs(etat, etat_precedent=''):
    """Booléens hérités déduits de l'état (copie de la règle de l'application, figée à la date de cette migration)."""
    base = etat_precedent if etat in ('supprime', 'renvoye') and etat_precedent in ETATS else etat
    return {
        'is_delete': etat == 'supprime',
        'is_validate2': base in ('valide_antenne', 'valide_province', 'actif', 'a_renouveler'),
        'is_validate3': base in ('actif', 'a_renouveler'),
        'renvoye': etat == 'renvoye' or (etat == 'supprime' and etat_precedent == 'renvoye'),
    }


def _par_lots(queryset, appliquer):
    """Applique ``appliquer(queryset_des_pk)`` par lots ; la sélection doit exclure les lignes déjà converties."""
    while True:
        pks = list(queryset.order_by('pk').values_list('pk', flat=True)[:LOT])
        if not pks:
            return
        appliquer(pks)


def vers_etat_unique(apps, schema_editor):
    from django.db.models import F
    Membre = apps.get_model('coptapp', 'Membre')
    base = Membre.objects.all()

    def maj(pks, **champs):
        base.filter(pk__in=pks).update(**champs)

    # 1. tout le monde -> saisi (valeur par défaut posée par 0061 ; on ne reprend ici que les valeurs inconnues)
    base.exclude(etat__in=ETATS).update(etat='saisi')
    # 2. validé antenne
    _par_lots(base.filter(etat='saisi', is_validate2=True), lambda pks: maj(pks, etat='valide_antenne'))
    # 3. actif (même sans is_validate2 : cas ambigu)
    _par_lots(base.filter(etat__in=('saisi', 'valide_antenne'), is_validate3=True), lambda pks: maj(pks, etat='actif'))

    # 4. renvoyé : l'état calculé aux étapes 1 à 3 est gardé dans etat_precedent
    def renvoyer(pks):
        maj(pks, etat_precedent=F('etat'))
        maj(pks, etat='renvoye')
    _par_lots(base.filter(renvoye=True).exclude(etat__in=('renvoye', 'supprime')), renvoyer)

    # 5. supprimé : d'abord etat_precedent = etat, puis etat = supprime (DEUX mises à jour séparées)
    def supprimer(pks):
        maj(pks, etat_precedent=F('etat'))
        maj(pks, etat='supprime')
    _par_lots(base.filter(is_delete=True).exclude(etat='supprime'), supprimer)


def vers_booleens(apps, schema_editor):
    """Sens inverse : recalcule is_delete, is_validate2, is_validate3, renvoye depuis etat (et etat_precedent)."""
    Membre = apps.get_model('coptapp', 'Membre')
    combinaisons = list(Membre.objects.values_list('etat', 'etat_precedent').distinct())
    for etat, precedent in combinaisons:
        Membre.objects.filter(etat=etat, etat_precedent=precedent).update(**miroirs(etat, precedent))


class Migration(migrations.Migration):

    dependencies = [
        ('coptapp', '0061_membre_etat_unique'),
    ]

    operations = [
        migrations.RunPython(vers_etat_unique, vers_booleens),
    ]
