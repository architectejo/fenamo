"""Écran de gestion de la configuration du site public (monté sous /contenu-site/configuration/)."""
from django.urls import path

from virtrine.views import config

urlpatterns = [
    path('', config, name="config"),
]
