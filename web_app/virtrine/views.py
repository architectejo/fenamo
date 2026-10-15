from django.shortcuts import render

from compte.permissions import editeur_requis
from virtrine.forms import ConfigForm
from virtrine.models import Config

#______________Configuration

@editeur_requis
def config(request):
    conf = Config.objects.last()  # None : le formulaire crée la configuration à l'enregistrement

    if request.method == 'POST':
        form = ConfigForm(request.POST, request.FILES, instance=conf)
        if form.is_valid():
            form.save()
    else:
        form = ConfigForm(instance=conf)
    return render(request, 'site/config.html', locals())
