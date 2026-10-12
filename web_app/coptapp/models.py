from django.db import models
from django.utils.translation import gettext_lazy as _
from compte.models import Compte
from coptapp.validators import valider_image, valider_piece
from datetime import date

# Create your models here.

#Configurations
class Province(models.Model):
    class Meta:
        verbose_name = _('coordination provinciale')
        verbose_name_plural = _('coordinations provinciales')

    user = models.ForeignKey(Compte, on_delete=models.RESTRICT, null=True, blank=True)
    nom = models.CharField(max_length=50, null=True, blank=True)
    sigle = models.CharField(max_length=5, null=True, blank=True)
    mise_a_jour = models.DateTimeField(auto_now=True, null=True, blank=True)
    
    def __str__(self):
        return f"{self.nom}"

class Ville(models.Model):
    user = models.ForeignKey(Compte, on_delete=models.RESTRICT, null=True, blank=True)
    province = models.ForeignKey(Province, on_delete=models.RESTRICT, null=True, blank=True)
    nom = models.CharField(max_length=50, null=True, blank=True)
    mise_a_jour = models.DateTimeField(auto_now=True, null=True, blank=True)
    
    def __str__(self):
        return f"{self.nom}"
    
class AssociationMembre(models.Model):
    class Meta:
        verbose_name = _('association membre')
        verbose_name_plural = _('associations membres')

    users = models.ManyToManyField(Compte, blank=True, related_name="users_of_structure")
    ville = models.ForeignKey(Ville, on_delete=models.SET_NULL, null=True, blank=True)
    province = models.ForeignKey(Province, on_delete=models.SET_NULL, null=True, blank=True)
    type_de_structure = models.CharField(max_length=50, null=True,blank=True, verbose_name=_("type d'association"))
    num_justice = models.CharField(max_length=50, null=True, blank=True, unique=True)
    capture_justice = models.ImageField(upload_to='./F92/', null=True, blank=True, validators=[valider_image])
    nom = models.CharField(max_length=255, null=True, blank=True)
    nom_responsable = models.CharField(max_length=255, null=True, blank=True)
    sigle = models.CharField(max_length=50, null=True, blank=True)
    logo = models.ImageField(upload_to='./logo/', null=True, blank=True, validators=[valider_image])
    adresse = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=25, default='+243...', null=True, blank=True)
    email = models.EmailField(max_length=100, default='@', null=True, blank=True)
    preuve_de_paiement = models.ImageField(upload_to='./frais/', null=True, blank=True, validators=[valider_image])
    twitter = models.CharField(max_length=500, null=True, blank=True)
    facebook = models.CharField(max_length=500, null=True, blank=True)
    instagram = models.CharField(max_length=500, null=True, blank=True)
    linkedin = models.CharField(max_length=500, null=True, blank=True)

    def __str__(self):
        return f"{self.sigle}"

class Antenne(models.Model):
    user = models.ForeignKey(Compte, on_delete=models.RESTRICT, null=True, blank=True)
    structure = models.ForeignKey(AssociationMembre, on_delete=models.RESTRICT, null=True, blank=True, verbose_name=_('association membre'))
    nom = models.CharField(max_length=50, null=True, blank=True)
    zone = models.CharField(max_length=50, null=True, blank=True)
    code = models.CharField(max_length=20, null=True, blank=True)
    mise_a_jour = models.DateTimeField(auto_now=True, null=True, blank=True)
    
    def __str__(self):
        return f"{self.nom}"


#Démande du client
class Membre(models.Model):
    idf = models.CharField(max_length=50, null=True, blank=True)
    password = models.CharField(max_length=100, null=True, blank=True)
    fiche_id = models.FileField(upload_to="./fiche_id/", null=True, blank=True, validators=[valider_piece])
    user = models.ForeignKey(Compte, on_delete=models.SET_NULL, null=True, blank=True)
    antenne = models.ForeignKey(Antenne, on_delete=models.SET_NULL, null=True, blank=True)
    ville = models.ForeignKey(Ville, on_delete=models.SET_NULL, null=True, blank=True)
    province = models.ForeignKey(Province, on_delete=models.SET_NULL, null=True, blank=True)
    structure = models.ForeignKey(to=AssociationMembre, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_('association membre'))
    code_parking = models.CharField(max_length=100, null=True, blank=True)
    nom = models.CharField(max_length=50, null=True, blank=True)
    date_naissance = models.DateField(null=True, blank=True)
    lieux_naissance = models.CharField(max_length=50, null=True, blank=True)
    genre = models.CharField(max_length=20, null=True, blank=True)
    titre = models.CharField(max_length=10, null=True, blank=True)
    fonction = models.CharField(max_length=30, null=True, blank=True)
    comite = models.CharField(max_length=50, null=True, blank=True)
    brevet = models.CharField(max_length=15, null=True, blank=True)
    etat_civil = models.CharField(max_length=50, null=True, blank=True)
    nom_epouse = models.CharField(max_length=50, null=True, blank=True)
    nation = models.CharField(max_length=50, default="Congolaise", null=True, blank=True)
    numero_carte_d_electeur = models.CharField(max_length=20, null=True, blank=True)
    numero_carte_de_membre = models.CharField(max_length=20, null=True, blank=True)
    nom_pere = models.CharField(max_length=50, null=True, blank=True)
    nom_mere = models.CharField(max_length=50, null=True, blank=True)
    village = models.CharField(max_length=30, null=True, blank=True)
    chefferie = models.CharField(max_length=30, null=True, blank=True)
    territoire = models.CharField(max_length=30, null=True, blank=True)
    province_origine = models.CharField(max_length=20, null=True, blank=True)
    photo = models.ImageField(upload_to='./', null=True, blank=True, validators=[valider_image])
    adresse = models.CharField(max_length=255, null=True, blank=True)
    telephone = models.CharField(max_length=20, null=True, blank=True)
    mail = models.EmailField(max_length=100, null=True, blank=True)
    categorie = models.CharField(max_length=20, null=True, blank=True)
    permis = models.CharField(max_length=20, null=True, blank=True)
    qualite = models.CharField(max_length=100, null=True, blank=True)
    autre_asb = models.CharField(max_length=255, null=True, blank=True)
    a_propos = models.TextField(blank=True, null=True)
    is_user = models.BooleanField(default=False, null=True, blank=True)
    is_delete = models.BooleanField(default=False)
    is_validate1 = models.BooleanField(default=True)
    is_validate2 = models.BooleanField(default=False)
    is_validate3 = models.BooleanField(default=False)
    is_membre = models.BooleanField(default=True)
    mise_a_jour = models.DateField(auto_now=True, null=True, blank=True)
    updated = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    
    def __str__(self):
        return f"{self.nom}"

class Moto(models.Model):
    class Meta:
        verbose_name = _('engin')
        verbose_name_plural = _('engins')

    user = models.ForeignKey(Compte, on_delete=models.RESTRICT, null=True, blank=True)
    structure = models.ForeignKey(to=AssociationMembre, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_('association membre'))
    proprietaire = models.ForeignKey(Membre, on_delete=models.RESTRICT, null=True, blank=True)
    antenne = models.ForeignKey(Antenne, on_delete=models.RESTRICT, null=True, blank=True)
    ville = models.ForeignKey(Ville, on_delete=models.RESTRICT, null=True, blank=True)
    province = models.ForeignKey(Province, on_delete=models.RESTRICT, null=True, blank=True)
    motard_id = models.CharField(max_length=50, null=True, blank=True)
    numero = models.CharField(max_length=20, null=True, blank=True)
    photo = models.ImageField(upload_to='./', null=True, blank=True, validators=[valider_image])
    abonnement = models.DateField()
    num_plaque = models.CharField(max_length=10, null=True, blank=True)
    num_moteur = models.CharField(max_length=50, null=True, blank=True)
    num_chassie = models.CharField(max_length=50, null=True, blank=True)
    marque = models.CharField(max_length=20, null=True, blank=True)
    couleur = models.CharField(max_length=20, null=True, blank=True)
    is_delete = models.BooleanField(default=False)
    mise_a_jour = models.DateField(auto_now=True, null=True, blank=True)
    
    def __str__(self):
        return f"{self.numero}"


class Communique(models.Model):
    user = models.ForeignKey(Compte, on_delete=models.RESTRICT, null=True, blank=True)
    membre = models.ForeignKey(Membre, on_delete=models.RESTRICT, null=True, blank=True)
    message = models.TextField(null=True, blank=True)
    mise_a_jour = models.DateTimeField(auto_now=True, null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.username}: {self.message}"


class Reaction(models.Model):
    user = models.ForeignKey(Compte, on_delete=models.CASCADE, null=True, blank=True)
    membre = models.ForeignKey(Membre, on_delete=models.RESTRICT, null=True, blank=True)
    communique = models.ForeignKey(Communique, on_delete=models.CASCADE, null=True, blank=True)
    reaction = models.TextField(blank=False, null=False)
    mise_a_jour = models.DateTimeField(auto_now=True, null=True, blank=True)


class Famille(models.Model):
    user = models.ForeignKey(Compte, on_delete=models.RESTRICT, null=True, blank=True)
    membre = models.ForeignKey(Membre, on_delete=models.RESTRICT, null=True, blank=True)
    priorite = models.IntegerField(null=True, blank=True)
    beneficiere = models.CharField(max_length=50, null=True, blank=True)
    qualite = models.CharField(max_length=10, null=True, blank=True)
    genre = models.CharField(max_length=20, null=True, blank=True)
    annee = models.IntegerField(null=True, blank=True)

class Notification(models.Model):
    user = models.ForeignKey(Compte, on_delete=models.RESTRICT, null=True, blank=True)
    membre = models.ForeignKey(Membre, on_delete=models.RESTRICT, null=True, blank=True)
    titre = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    is_validate = models.BooleanField(default=False, null=True, blank=True)
    mise_a_jour = models.DateTimeField(auto_now=True, null=True, blank=True)
    
class Error(models.Model):
    user = models.ForeignKey(Compte, on_delete=models.CASCADE, null=True, blank=True)
    error404 = models.BooleanField(default=False, null=True, blank=True)