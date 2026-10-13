"""Déplace les pièces et photos des membres de MEDIA_ROOT vers PRIVATE_MEDIA_ROOT (§ 9.4). Rejouable, sans perte."""
from django.core.management.base import BaseCommand, CommandError

from coptapp.services.fichiers_prives import deplacer_fichiers_prives


class Command(BaseCommand):
    help = ("Copie chaque fichier privé vers PRIVATE_MEDIA_ROOT, vérifie les hachages SHA-256, puis supprime la source. "
            "Utiliser --dry-run pour voir ce qui serait fait.")

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Ne rien copier ni supprimer : afficher le plan.')

    def handle(self, *args, **options):
        rapport = deplacer_fichiers_prives(dry_run=options['dry_run'])
        prefixe = 'Simulation : ' if options['dry_run'] else ''
        self.stdout.write(f"{prefixe}{len(rapport['deplaces'])} fichier(s) déplacé(s), {len(rapport['deja_deplaces'])} déjà "
                          f"en place, {len(rapport['absents'])} absent(s), {len(rapport['conflits'])} conflit(s).")
        for champ, nom in rapport['absents']:
            self.stdout.write(self.style.WARNING(f'  absent : {champ} {nom}'))
        for champ, nom, raison in rapport['conflits']:
            self.stdout.write(self.style.ERROR(f'  conflit ({raison}) : {champ} {nom}'))
        if rapport['conflits']:
            raise CommandError('Des fichiers n\'ont pas pu être déplacés sans risque : rien n\'a été supprimé pour eux.')
