"""Tableau de bord (coque du lot 1). Les indicateurs par périmètre arrivent avec les lots 2 et 4 (F-16, F-51)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def tableau_bord(request):
    return render(request, 'coptapp/tableau_bord/tableau_bord.html')
