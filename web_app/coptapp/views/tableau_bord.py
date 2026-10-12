"""Tableau de bord. Les indicateurs par périmètre définitif arrivent avec le sous-lot 2e (F-16, F-51)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from coptapp.services.tableau_bord import indicateurs_tableau_bord


@login_required
def tableau_bord(request):
    """Page d'accueil. Contexte : ``indicateurs`` (dictionnaire de coptapp.services.tableau_bord.indicateurs_tableau_bord :
    actifs, valides_antenne, saisis, en_attente_total, engins, associations, en_attente, graphique), calculé dans le
    périmètre provisoire du compte. Le gabarit n'appelle plus de balise pour les obtenir."""
    return render(request, 'coptapp/tableau_bord/tableau_bord.html', {'indicateurs': indicateurs_tableau_bord(request.user)})
