"""Données du site public : slugs uniques des articles existants, copie des téléphones et des partenaires de Config.

Additive et réversible : les anciennes colonnes (phone1..7, partenaire1..7, link1..7) sont conservées ; les articles existants restent en
BROUILLON (valeur par défaut du statut : rien n'est publié automatiquement) ; ``integration_code`` n'est ni modifié ni exposé.
"""
from django.db import migrations
from django.utils.text import slugify


def remplir(apps, schema_editor):
    Article = apps.get_model('virtrine', 'Article')
    Config = apps.get_model('virtrine', 'Config')
    Telephone = apps.get_model('virtrine', 'TelephoneSite')
    Partenaire = apps.get_model('virtrine', 'Partenaire')
    pris = set(Article.objects.exclude(slug=None).values_list('slug', flat=True))
    for article in Article.objects.filter(slug=None).order_by('pk'):
        base = slugify(article.titre or '')[:170] or 'article'
        slug, n = base, 1
        while slug in pris:
            n += 1
            slug = f'{base}-{n}'
        pris.add(slug)
        Article.objects.filter(pk=article.pk).update(slug=slug)
    config = Config.objects.order_by('pk').first()
    if config is None:
        return
    if not Telephone.objects.exists():
        for i in range(1, 8):
            numero = (getattr(config, f'phone{i}') or '').strip()
            if numero:
                Telephone.objects.create(numero=numero, ordre=i)
    if not Partenaire.objects.exists():
        for i in range(1, 8):
            nom = (getattr(config, f'partenaire{i}') or '').strip()
            if nom:
                Partenaire.objects.create(nom=nom[:255], lien=(getattr(config, f'link{i}') or '').strip()[:255], ordre=i)


def retirer(apps, schema_editor):
    """Retour arrière : les copies sont supprimées (les colonnes d'origine n'ont jamais été touchées) ; les slugs restent (inoffensifs)."""
    apps.get_model('virtrine', 'TelephoneSite').objects.all().delete()
    apps.get_model('virtrine', 'Partenaire').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [('virtrine', '0020_site_public_schema')]

    operations = [migrations.RunPython(remplir, retirer)]
