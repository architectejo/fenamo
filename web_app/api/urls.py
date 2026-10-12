"""API `/api/v1/` (site public, puis mobile). Seule la vue de santé existe pour l'instant."""
from django.urls import path

from api import views

app_name = 'api'

urlpatterns = [
    path('sante/', views.sante, name='sante'),  # adresse du contrat
    path('', views.sante, name='racine'),  # conservée : sondes de supervision déjà configurées
]
