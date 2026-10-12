from django.urls import include, path
from virtrine.views import actualy, article, about, config, home, politique, portail

urlpatterns = [
    path('', home, name="home"),
    path('article/<int:id>', article, name="vue-article"),
    path('a-propos-de-nous/', about, name="about"),
    path('activites/', actualy, name="news"),
    path('configuration/', config, name="config"),
    path('portail/', portail, name="portail"),
    path('confidentiel/', politique, name="politique"),
]