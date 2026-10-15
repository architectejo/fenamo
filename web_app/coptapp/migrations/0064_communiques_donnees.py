"""Communiqués existants : titre dérivé du début du message, date de publication = dernière date connue, sans ciblage (= national).
Additive et réversible (le retour arrière ne retire rien : les colonnes sont supprimées par la migration 0063)."""
from django.db import migrations
from django.utils import timezone


def remplir(apps, schema_editor):
    Communique = apps.get_model('coptapp', 'Communique')
    for c in Communique.objects.filter(titre='').order_by('pk'):
        premiere = ((c.message or '').strip().splitlines() or [''])[0].strip()
        titre = premiere[:117] + '…' if len(premiere) > 120 else premiere
        Communique.objects.filter(pk=c.pk).update(titre=titre or 'Communiqué', publie_le=c.mise_a_jour or c.publie_le or timezone.now())


class Migration(migrations.Migration):

    dependencies = [('coptapp', '0063_communiques_ciblage_lecture')]

    operations = [migrations.RunPython(remplir, migrations.RunPython.noop)]
