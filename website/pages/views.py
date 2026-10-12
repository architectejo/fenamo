from django.shortcuts import render
from django.utils.translation import gettext as _


def accueil(request):
    return render(
        request,
        "pages/accueil.html",
        {
            "page_title": _("Accueil"),
            "page_description": _(
                "Fédération Nationale des Associations des Motocyclistes Taximen de la RDC."
            ),
            "noindex": False,  # une page de vérification ou de suivi passera True
        },
    )
