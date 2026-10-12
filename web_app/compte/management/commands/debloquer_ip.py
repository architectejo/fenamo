"""Débloque une adresse IP : efface ses tentatives axes ET son journal d'échecs (base du verrou par IP seule).

`axes_reset_ip` seul ne suffit pas : il laisse le journal d'échecs, que compte/services/verrou.py compte.
"""
from axes.models import AccessAttempt, AccessFailureLog
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Débloque une ou plusieurs adresses IP (verrou axes et verrou par adresse IP seule)."

    def add_arguments(self, parser):
        parser.add_argument('ip', nargs='+', type=str)

    def handle(self, *args, **options):
        for ip in options['ip']:
            tentatives, _ = AccessAttempt.objects.filter(ip_address=ip).delete()
            echecs, _ = AccessFailureLog.objects.filter(ip_address=ip).delete()
            self.stdout.write(f"{ip} : {tentatives} tentative(s) et {echecs} échec(s) effacé(s).")
