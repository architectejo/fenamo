"""Journal d'activités (F-71) : lecture seule, super-utilisateur. Page complète ou zone HTMX (veut_fragment)."""
from django.shortcuts import render
from django.views.decorators.http import require_GET

from compte import roles
from compte import roles
from compte.models import JournalAction
from coptapp.models import Antenne, Province
from coptapp.models import Antenne, Province
from compte.permissions import superuser_requis
from compte.services.journal_lecture import lister_journal
from fenamo.htmx import veut_fragment


@require_GET
@superuser_requis
def journal(request):
    filtres = {cle: (request.GET.get(cle) or '').strip() for cle in ('q', 'action', 'role', 'coordination', 'antenne', 'du', 'au')}
    page = lister_journal(filtres, request.GET.get('page'))
    contexte = {'page_obj': page, 'filtres': filtres, 'filtres_actifs': any(filtres.values()), 'actions': JournalAction.Action.choices,
                'roles': roles.CHOICES, 'coordinations': Province.objects.filter(code__isnull=False).order_by('ordre', 'nom'),
                'antennes': Antenne.objects.exclude(nom=None).order_by('nom')}
    modele = 'compte/journal/partials/_zone.html' if veut_fragment(request) else 'compte/journal/journal.html'
    return render(request, modele, contexte)
