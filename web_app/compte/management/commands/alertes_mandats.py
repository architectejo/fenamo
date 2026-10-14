"""Alertes de fin de mandat des nominations (cron quotidien, sous-lot 2e).

Exemple : python manage.py alertes_mandats --jours 60 --dry-run
Envoie une notification à celui qui a nommé (sinon aux présidents) 60 jours avant la fin du mandat, puis à l'échéance. Idempotente
(``alerte_envoyee_le``). Liste les nominations échues. NE DÉSACTIVE RIEN : les droits restent actifs jusqu'à clôture manuelle.
"""
from django.core.management.base import BaseCommand

from compte.services.nominations import JOURS_ALERTE, alertes_de_mandat


class Command(BaseCommand):
    help = "Alertes de fin de mandat (60 jours avant et à l'échéance), sans rien désactiver."

    def add_arguments(self, parser):
        parser.add_argument('--jours', type=int, default=JOURS_ALERTE, help='Délai de la première alerte (défaut 60).')
        parser.add_argument('--dry-run', action='store_true', help="Ne rien envoyer ni enregistrer : afficher ce qui serait fait.")

    def handle(self, *args, **options):
        rapport = alertes_de_mandat(jours=options['jours'], dry_run=options['dry_run'])
        prefixe = 'Simulation : ' if options['dry_run'] else ''
        self.stdout.write(f"{prefixe}{len(rapport['envoyees'])} alerte(s) à envoyer, {len(rapport['a_venir'])} mandat(s) bientôt échu(s), "
                          f"{len(rapport['echues'])} échu(s) toujours actif(s).")
        for n in rapport['echues']:
            self.stdout.write(self.style.WARNING(
                f"  échue : {n.compte.username} ({n.role}) depuis le {n.fin:%d/%m/%Y} : droits actifs jusqu'à clôture manuelle"))
        for n in rapport['a_venir']:
            self.stdout.write(f"  à venir : {n.compte.username} ({n.role}) le {n.fin:%d/%m/%Y}")
