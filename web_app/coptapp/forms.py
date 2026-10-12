from django import forms
from coptapp.models import *
from django.contrib.auth import get_user_model

User = get_user_model()
# Form of structure
class StructureForm(forms.ModelForm):
    ville = forms.ModelChoiceField(queryset=Ville.objects.order_by('nom').exclude(nom=None), label='Antenne', empty_label='Selectionnez une antenne')
    class Meta:
        model = Structure
        exclude = ['users','province']
        labels = {
            'nom':'Dénomination',
            'ville':'Antenne',
            'num_justice':'N° Justice (F92 ou Personnalité juridique)',
            'nom_responsable':"Nom du responsable"
        }

    def __init__(self, *args, **kwargs):
        super(StructureForm, self).__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'

class StructureIdentifyForm(forms.ModelForm):
    province = forms.ModelChoiceField(queryset=Province.objects.order_by('nom').exclude(nom=None), label='Province', required=True)
    types = [
        ('NATIONALE','NATIONALE'),
        ('PROVINCIALE','PROVINCIALE'),
        ('TERRITORIALE','TERRITORIALE')
    ]
    type_de_structure = forms.ChoiceField(choices=types, label="Type d'association")
    class Meta:
        model = Structure
        exclude = ['users','ville']
        labels = {
            'nom':'Dénomination',
            'type_de_structure':"Type d'association",
            'num_justice':'N° Justice (F92 ou PERSONNALITE JURIDIQUE)',
            'capture_justice':"Capture (F92 ou PERSONNALITE JURIDIQUE)",
            'preuve_de_paiement':"Capture de la preuve de paiement"
        }

    def __init__(self, *args, **kwargs):
        super(StructureIdentifyForm, self).__init__(*args, **kwargs)
        self.fields['capture_justice'].required = True
        self.fields['preuve_de_paiement'].required = True
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'

# Form of membre
class MembreForm(forms.ModelForm):
    genre_liste = [('HOMME','HOMME'),('FEMME','FEMME')]
    qualites_liste = [('PROPRIETAIRE','PROPRIETAIRE'),('MOTARD ET PROPRIETAIRE','MOTARD ET PROPRIETAIRE')]
    titre_liste = [('MR','MR'),('MME','MME'),('MLLE','MLLE')]
    fonction_liste = [('Membre simple','Membre simple'),('Membre du comité','Membre du comité'),('Associe','Associe')]
    comite_liste = [('SUPERVISION MOBILE','SUPERVISION MOBILE'),('SUPERVISION PARKING','SUPERVISION PARKING'),('ANTENNE','ANTENNE'),('COORDINATION PROVINCIAL','COORDINATION PROVINCIAL'),('COMITE NATIONAL','COMITE NATIONAL'),('ZONE OPS','ZONE OPS')]
    etat_civil_liste = [('Celibataire','Celibataire'),('Marié(e)','Marié(e)'),('Divorcé','Divorcé'),('Veuf(Veuve)','Veuf(Veuve)')]
    categorie_liste = [('H','H'),('F','F'),('S','S')]
    genre = forms.ChoiceField(choices=genre_liste)
    qualite = forms.ChoiceField(choices=qualites_liste)
    titre = forms.ChoiceField(choices=titre_liste)
    fonction = forms.ChoiceField(choices=fonction_liste)
    comite = forms.ChoiceField(choices=comite_liste, label="Rôle")
    etat_civil = forms.ChoiceField(choices=etat_civil_liste)
    categorie =forms.ChoiceField(choices=categorie_liste, label="Catégorie")
    date_naissance = forms.DateField(widget=forms.DateInput)
    class Meta:
        model = Membre
        exclude = ['user','structure','province','antenne','is_delete','is_validate1','is_validate2','is_validate3','is_membre','is_user','a_propos','autre_asb']
        labels = {
            'nom':"Nom complet",
            'date_naissance':"Date de naissance",
            'comite':"Rôle",
            'brevet':"Numéro brevet",
            'nom_epouse':"Nom de l'épouse",
            'mail':"E-mail",
        }

    def __init__(self, *args, **kwargs):
        structure = kwargs.pop('structure', None)
        super(MembreForm, self).__init__(*args, **kwargs)
        self.fields['ville'].empty_label = "Antenne"
        self.fields['ville'].label = "Antenne"

        if structure: 
            self.fields['ville'].queryset = Ville.objects.filter(province=structure.province)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'


# Form of membre
class MembreFenamoForm(forms.ModelForm):
    genre_liste = [('HOMME','HOMME'),('FEMME','FEMME')]
    qualites_liste = [('PROPRIETAIRE','PROPRIETAIRE'),('MOTARD ET PROPRIETAIRE','MOTARD ET PROPRIETAIRE')]
    titre_liste = [('MR','MR'),('MME','MME'),('MLLE','MLLE')]
    fonction_liste = [('Membre simple','Membre simple'),('Membre du comité','Membre du comité'),('Associe','Associe')]
    comite_liste = [('SUPERVISION MOBILE','SUPERVISION MOBILE'),('SUPERVISION PARKING','SUPERVISION PARKING'),('ANTENNE','ANTENNE'),('COORDINATION PROVINCIAL','COORDINATION PROVINCIAL'),('COMITE NATIONAL','COMITE NATIONAL'),('ZONE OPS','ZONE OPS')]
    etat_civil_liste = [('Celibataire','Celibataire'),('Marié(e)','Marié(e)'),('Divorcé','Divorcé'),('Veuf(Veuve)','Veuf(Veuve)')]
    categorie_liste = [('H','H'),('F','F'),('S','S')]
    genre = forms.ChoiceField(choices=genre_liste)
    qualite = forms.ChoiceField(choices=qualites_liste)
    titre = forms.ChoiceField(choices=titre_liste)
    fonction = forms.ChoiceField(choices=fonction_liste)
    comite = forms.ChoiceField(choices=comite_liste, label="Rôle")
    etat_civil = forms.ChoiceField(choices=etat_civil_liste)
    categorie =forms.ChoiceField(choices=categorie_liste, label="Catégorie")
    date_naissance = forms.DateField(widget=forms.DateInput)
    class Meta:
        model = Membre
        exclude = ['user','structure','idf','password','ville','antenne','is_delete','is_validate1','is_validate2','is_validate3','is_membre','is_user','a_propos','autre_asb']
        labels = {
            'nom':"Nom complet",
            'date_naissance':"Date de naissance",
            'comite':"Rôle",
            'brevet':"Numéro brevet",
            'nom_epouse':"Nom de l'épouse",
            'mail':"E-mail",
        }

    def __init__(self, *args, **kwargs):
        super(MembreFenamoForm, self).__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'

# Form of antenne
class AntenneForm(forms.ModelForm):
    class Meta:
        model = Antenne
        exclude = ['user','structure']
        labels = {
            'nom':"Nom de l'antenne",
            'zone':"Zone opérationnelle"
        }

    def __init__(self, *args, **kwargs):
        super(AntenneForm, self).__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'