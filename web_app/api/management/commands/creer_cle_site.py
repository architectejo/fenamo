from django.core.management.base import BaseCommand, CommandError

from api.services.cles import CleSiteErreur, creer_cle


class Command(BaseCommand):
    help = "Crée une clé d'accès du site public à l'API (affichée UNE seule fois ; deux clés actives au plus)."

    def add_arguments(self, parser):
        parser.add_argument('--nom', required=True, help="Nom de la clé, par exemple « Site public »")

    def handle(self, *args, **options):
        try:
            objet, cle = creer_cle(options['nom'])
        except CleSiteErreur as erreur:
            raise CommandError(str(erreur))
        self.stdout.write(f"Clé « {objet.nom} » créée (préfixe {objet.prefixe}). Copiez-la maintenant : elle ne sera plus affichée.")
        self.stdout.write(cle)
