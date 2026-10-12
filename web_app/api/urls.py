"""API `/api/v1/` (site public, puis mobile). Seule la vue de santé existe pour l'instant."""
from django.urls import path

from api import views

app_name = 'api'

urlpatterns = [
    path('', views.sante, name='sante'),
]
