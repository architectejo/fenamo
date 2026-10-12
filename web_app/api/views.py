from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def sante(request):
    """Vue de santé : ne renvoie aucune donnée métier.

    TODO : protection par la clé du site pour les points d'accès /api/v1/site/.
    """
    return JsonResponse({'statut': 'ok', 'version': 'v1'})
