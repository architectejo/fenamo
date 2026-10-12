from django.urls import path
from mobapp.views import *

urlpatterns = [
    path('', home, name="home-mob"),
    path('espace/<int:id>', session, name="session"),
    path('register/', register, name="register"),
    path('data/<int:id>', data_membre, name="data"),
    path('attribut-str/<int:id>/<int:id_str>', attribut_str, name="attribut-str"),
    path('attribut-ville/<int:id>/<int:id_ville>', attribut_ville, name="attribut-ville"),
]