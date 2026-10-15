from django.core.management.base import BaseCommand, CommandError

from api.services.cles import CleSiteErreur, revoquer_cle


class Command(BaseCommand):
    help = "Révoque une clé du site (effet immédiat) à partir de son préfixe de 8 caractères."

    def add_arguments(self, parser):
        parser.add_argument('prefixe')

    def handle(self, *args, **options):
        try:
            objet = revoquer_cle(options['prefixe'])
        except CleSiteErreur as erreur:
            raise CommandError(str(erreur))
        self.stdout.write(f"Clé « {objet.nom} » (préfixe {objet.prefixe}) révoquée.")
