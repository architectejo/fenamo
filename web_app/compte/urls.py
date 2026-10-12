from django.urls import path

from compte.views import add_user, adminer, connexion, deconnexion, delete_user

urlpatterns = [
    path('connexion/', connexion, name="application"),
    path('deconnexion/', deconnexion, name="deconnexion"),  # TODO lot 2 : POST + CSRF
    path('membres/<int:id>/creer-compte/', adminer, name="adminer"),  # TODO lot 2 : POST + CSRF (crée un compte en GET)
    path('comptes/ajouter/', add_user, name="add-user"),
    path('comptes/desactiver/', delete_user, name="delete-user"),  # POST seulement ; supprime le compte connecté
]
