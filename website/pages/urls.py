from django.urls import path

from . import views

app_name = "pages"

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("a-propos/", views.a_propos, name="a-propos"),
    path("organisation/comite/", views.comite, name="comite"),
    path("organisation/coordinations/", views.coordinations, name="coordinations"),
    path("documents/", views.documents, name="documents"),
    path("application/", views.application, name="application"),
    path("actualites/", views.actualites, name="actualites"),
    path("actualites/<slug:slug>/", views.article, name="article"),
    path("galerie/", views.galerie, name="galerie"),
    path("contact/", views.contact, name="contact"),
    path("adhesion/", views.adhesion, name="adhesion"),
    path("verifier/", views.verifier, name="verifier"),
    path("mentions-legales/", views.mentions_legales, name="mentions-legales"),
    path("confidentialite/", views.confidentialite, name="confidentialite"),
    path("telecharger/<slug:type_>/<slug:slug>/", views.telecharger, name="telecharger"),
]
