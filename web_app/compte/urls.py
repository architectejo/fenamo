from django.urls import path

from compte.views import add_user, adminer, connexion, deconnexion, securite

urlpatterns = [
    path('connexion/', connexion, name="application"),
    path('deconnexion/', deconnexion, name="deconnexion"),  # POST seulement
    path('membres/<int:id>/creer-compte/', adminer, name="adminer"),  # POST seulement, super-utilisateur
    path('comptes/ajouter/', add_user, name="add-user"),  # super-utilisateur
    path('mon-compte/securite/', securite, name="securite"),
]
