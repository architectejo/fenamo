from django.urls import path

from compte.views import add_user, adminer, connexion, deconnexion, delete_user

urlpatterns = [
    path('connexion/', connexion, name="application"),
    path('deconnexion/', deconnexion, name="deconnexion"),
    path('membres/<int:id>/creer-compte/', adminer, name="adminer"),
    path('comptes/ajouter/', add_user, name="add-user"),
    path('comptes/desactiver/', delete_user, name="delete-user"),  # POST seulement ; supprime le compte connecté
]
