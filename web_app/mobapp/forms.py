from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from coptapp.models import Membre, Moto, Province


class MotoFormRegister(forms.ModelForm):
    couleur_liste = [('ROUGE','ROUGE'),('BLEU','BLEU'),('JAUNE','JAUNE'),('NOIRE','NOIRE'),('VERTE','VERTE'),('ORANGE','ORANGE')]
    couleur = forms.ChoiceField(choices=couleur_liste)
    class Meta:
        model = Moto
        # Liste blanche (jamais d'exclude : formulaire public)
        fields = ('photo', 'num_plaque', 'num_moteur', 'num_chassie', 'marque', 'couleur')
        labels = {
            'photo': _("Image"),
            'num_plaque': _("Numéro de plaque"),
            'num_moteur': _("Numéro de moteur"),
            'num_chassie': _("Numéro de châssis"),
        }
    def __init__(self, *args, **kwargs):
        super(MotoFormRegister, self).__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control text-center'


class MembreFormRegister(forms.ModelForm):
    genre_liste = [('HOMME','HOMME'),('FEMME','FEMME')]
    qualites_liste = [('PROPRIETAIRE','PROPRIETAIRE'),('MOTARD ET PROPRIETAIRE','MOTARD ET PROPRIETAIRE')]
    genre = forms.ChoiceField(choices=genre_liste)
    qualite = forms.ChoiceField(choices=qualites_liste)
    province = forms.ModelChoiceField(queryset=Province.objects.order_by('nom').exclude(nom=None), label=_('Province'), required=True)
    class Meta:
        model = Membre
        # Liste blanche (jamais d'exclude : formulaire public anonyme)
        fields = (
            'province',
            'nom',
            'date_naissance',
            'lieux_naissance',
            'genre',
            'titre',
            'fonction',
            'comite',
            'brevet',
            'etat_civil',
            'nom_epouse',
            'nation',
            'numero_carte_d_electeur',
            'nom_pere',
            'nom_mere',
            'village',
            'chefferie',
            'territoire',
            'province_origine',
            'photo',
            'adresse',
            'telephone',
            'mail',
            'categorie',
            'permis',
            'qualite',
        )
        labels = {
            'nom': _("Nom complet"),
            'date_naissance': _("Date de naissance"),
            'lieux_naissance': _("Lieu de naissance"),
            'comite': _("Comité"),
            'brevet': _("Brevet de formation"),
            'nom_epouse': _("Nom de l'épouse (si marié)"),
            'nation': _("Nationalité"),
            'numero_carte_d_electeur': _("Numéro de carte d'électeur"),
            'nom_pere': _("Nom du père"),
            'province_origine': _("Province d'origine"),
            'telephone': _("Téléphone"),
            'mail': _("E-mail"),
            'categorie': _("Catégorie"),
            'qualite': _("Qualité"),
        }

    def __init__(self, *args, **kwargs):
        super(MembreFormRegister, self).__init__(*args, **kwargs)

        #self.helper = FormHelper()
        # Ajouter une classe CSS à tous les champs du formulaire
        for field_name, field in self.fields.items():
            #self.helper.layout = Layout(Div(field, css_class='col-12 col-sm-6 py-2 wow fadeInRight'))
            field.widget.attrs['class'] = 'form-control text-center'

class InscriptionMobileForm(MembreFormRegister):
    """Inscription publique /mob/register/ : le formulaire de membre (liste blanche) plus le mot de passe de l'espace mobile
    (saisi deux fois, règles de mot de passe de Django, enregistré HACHÉ) et un champ piège caché contre les robots :
    un champ rempli par un robot rejette l'inscription sans rien enregistrer."""

    password1 = forms.CharField(label=_('Mot de passe'), widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    password2 = forms.CharField(label=_('Confirmez le mot de passe'), widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    piege = forms.CharField(required=False, widget=forms.HiddenInput, label='')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nom in ('password1', 'password2'):
            self.fields[nom].widget.attrs['class'] = 'form-control text-center'

    def clean(self):
        donnees = super().clean()
        if donnees.get('piege'):
            raise forms.ValidationError(_("Inscription refusée."))
        mot1, mot2 = donnees.get('password1'), donnees.get('password2')
        if mot1 and mot2 and mot1 != mot2:
            self.add_error('password2', _("Les deux mots de passe ne correspondent pas."))
        elif mot1:
            try:
                validate_password(mot1)
            except ValidationError as erreur:
                self.add_error('password1', erreur)
        return donnees
