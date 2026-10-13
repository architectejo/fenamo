from django import forms
from coptapp.models import *
from django.contrib.auth import get_user_model

User = get_user_model()
# Formulaires de l'association membre et de l'antenne : LISTE BLANCHE de champs (jamais d'exclude).
class AssociationMembreForm(forms.ModelForm):
    ville = forms.ModelChoiceField(queryset=Ville.objects.order_by('nom').exclude(nom=None), label='Antenne', empty_label='Selectionnez une antenne')
    class Meta:
        model = AssociationMembre
        fields = ('ville', 'type_de_structure', 'num_justice', 'capture_justice', 'nom', 'nom_responsable', 'sigle', 'logo', 'adresse', 'phone', 'email', 'preuve_de_paiement', 'twitter', 'facebook', 'instagram', 'linkedin')
        labels = {
            'nom':'Dénomination',
            'ville':'Antenne',
            'num_justice':'N° Justice (F92 ou Personnalité juridique)',
            'nom_responsable':"Nom du responsable"
        }

    def __init__(self, *args, **kwargs):
        super(AssociationMembreForm, self).__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'

class AssociationMembreIdentifyForm(forms.ModelForm):
    province = forms.ModelChoiceField(queryset=Province.objects.order_by('nom').exclude(nom=None), label='Province', required=True)
    types = [
        ('NATIONALE','NATIONALE'),
        ('PROVINCIALE','PROVINCIALE'),
        ('TERRITORIALE','TERRITORIALE')
    ]
    type_de_structure = forms.ChoiceField(choices=types, label="Type d'association")
    class Meta:
        model = AssociationMembre
        fields = ('province', 'type_de_structure', 'num_justice', 'capture_justice', 'nom', 'nom_responsable', 'sigle', 'logo', 'adresse', 'phone', 'email', 'preuve_de_paiement', 'twitter', 'facebook', 'instagram', 'linkedin')
        labels = {
            'nom':'Dénomination',
            'type_de_structure':"Type d'association",
            'num_justice':'N° Justice (F92 ou PERSONNALITE JURIDIQUE)',
            'capture_justice':"Capture (F92 ou PERSONNALITE JURIDIQUE)",
            'preuve_de_paiement':"Capture de la preuve de paiement"
        }

    def __init__(self, *args, **kwargs):
        super(AssociationMembreIdentifyForm, self).__init__(*args, **kwargs)
        self.fields['capture_justice'].required = True
        self.fields['preuve_de_paiement'].required = True
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'

# Formulaires de membre : LISTE BLANCHE de champs (jamais d'exclude : un champ ajouté au modèle ne doit pas devenir
# modifiable par un POST forgé).
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
        fields = (
            'fiche_id',
            'ville',
            'code_parking',
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
            'numero_carte_de_membre',
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
        fields = (
            'fiche_id',
            'province',
            'code_parking',
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
            'numero_carte_de_membre',
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
        fields = ('nom', 'zone', 'code', 'type', 'coordination')
        labels = {
            'nom':"Nom de l'antenne",
            'zone':"Zone opérationnelle"
        }

    def __init__(self, *args, **kwargs):
        super(AntenneForm, self).__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'


# Modification d'un membre depuis la fiche (F-21) : liste blanche, `nom` et la date de naissance obligatoires.
CHAMPS_MODIFIABLES = (
    'nom', 'a_propos', 'date_naissance', 'genre', 'titre', 'fonction', 'comite', 'nation', 'brevet', 'etat_civil',
    'adresse', 'telephone', 'mail', 'categorie', 'permis', 'qualite', 'autre_asb', 'nom_epouse', 'numero_carte_d_electeur',
    'numero_carte_de_membre', 'nom_pere', 'nom_mere', 'village', 'chefferie', 'territoire', 'province_origine',
)
# Noms envoyés par la modale de la fiche -> champs du modèle (utilisés par MembreModificationForm).
ALIAS_POST = {'about': 'a_propos', 'date': 'date_naissance', 'autre_asbl': 'autre_asb', 'epouse': 'nom_epouse'}
OBLIGATOIRES = ('nom', 'date_naissance')


class MembreModificationForm(forms.ModelForm):
    """Formulaire de modification : `nom` et la date de naissance sont obligatoires (erreur de formulaire s'ils
    manquent) ; un autre champ absent du POST garde sa valeur actuelle. Date au format JJ-MM-AAAA (ou AAAA-MM-JJ)."""

    date_naissance = forms.DateField(input_formats=['%d-%m-%Y', '%Y-%m-%d'], required=True)

    class Meta:
        model = Membre
        fields = CHAMPS_MODIFIABLES + ('photo',)

    def __init__(self, data=None, files=None, instance=None, **kwargs):
        if data is not None:
            data = data.copy()
            for alias, champ in ALIAS_POST.items():
                if alias in data and champ not in data:
                    data[champ] = data[alias]
            for champ in CHAMPS_MODIFIABLES:
                if champ not in data and champ not in OBLIGATOIRES and instance is not None:
                    valeur = getattr(instance, champ)
                    data[champ] = '' if valeur is None else str(valeur)
        super().__init__(data, files, instance=instance, **kwargs)
        self.fields['nom'].required = True


# ---------------------------------------------------------------- proche et engin (F-26, F-35)

class FamilleForm(forms.Form):
    """Proche d'un membre. Longueurs maximales alignées sur le modèle `Famille` (une valeur trop longue est une erreur
    de formulaire, jamais une DataError de la base) ; année entière."""

    nom = forms.CharField(max_length=Famille._meta.get_field('beneficiere').max_length)
    qualite = forms.CharField(max_length=Famille._meta.get_field('qualite').max_length)
    genre = forms.CharField(max_length=Famille._meta.get_field('genre').max_length)
    annee = forms.IntegerField(min_value=1, max_value=9999)


class EnginForm(forms.Form):
    """Engin (plaque, marque, couleur, châssis, moteur). Longueurs maximales alignées sur le modèle `Moto` ; les
    champs doivent être envoyés (ils peuvent rester vides, comme dans l'écran hérité)."""

    plaque = forms.CharField(max_length=Moto._meta.get_field('num_plaque').max_length, required=False)
    marque = forms.CharField(max_length=Moto._meta.get_field('marque').max_length, required=False)
    couleur = forms.CharField(max_length=Moto._meta.get_field('couleur').max_length, required=False)
    chassie = forms.CharField(max_length=Moto._meta.get_field('num_chassie').max_length, required=False)
    moteur = forms.CharField(max_length=Moto._meta.get_field('num_moteur').max_length, required=False)

    def clean(self):
        donnees = super().clean()
        absents = [nom for nom in self.fields if nom not in self.data]
        if absents:
            raise forms.ValidationError(MESSAGE_CHAMPS_MANQUANTS)
        return donnees


MESSAGE_CHAMPS_MANQUANTS = "Renseignez tous les champs du formulaire."


def erreurs_en_texte(formulaire):
    """Texte unique des erreurs d'un formulaire (champ : message), pour le message d'une vue."""
    return ' '.join(f"{champ} : {' '.join(messages)}" if champ != '__all__' else ' '.join(messages)
                    for champ, messages in formulaire.errors.items())
