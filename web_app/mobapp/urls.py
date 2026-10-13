from django.contrib.auth.decorators import login_not_required
from django.urls import path
from mobapp.views import *

# /mob/ garde sa propre session (adaptée au sous-lot 2c) : exempté de la connexion obligatoire.

urlpatterns = [
    path('', login_not_required(home), name="home-mob"),
    path('espace/<int:id>', login_not_required(session), name="session"),
    path('deconnexion/', login_not_required(deconnexion), name="deconnexion-mob"),
    path('register/', login_not_required(register), name="register"),
    path('photo/<int:id>', login_not_required(photo_membre), name="photo-mob"),
    path('data/<int:id>', login_not_required(data_membre), name="data"),
    path('attribut-str/<int:id>/<int:id_str>', login_not_required(attribut_str), name="attribut-str"),
    path('attribut-ville/<int:id>/<int:id_ville>', login_not_required(attribut_ville), name="attribut-ville"),
]