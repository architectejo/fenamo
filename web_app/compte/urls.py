from django.urls import path
from compte.views import add_user, adminer, connexion, deconnexion, delete_user


urlpatterns = [
    path('', connexion, name="application"),
    path('deconnexion/', deconnexion, name="deconnexion"),
    path('admin-manager/<int:id>', adminer, name="adminer"),
    path('add-user/', add_user, name="add-user"),
    path('delete-user/', delete_user, name="delete-user"),
]