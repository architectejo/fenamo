from django.db import models
from compte.models import Compte
from coptapp.validators import valider_image
# Create your models here.

class Galery(models.Model):
    principale = models.BooleanField(default=False, null=True, blank=True)
    image = models.ImageField(upload_to="./article", null=True, blank=True, validators=[valider_image])
    is_delete = models.BooleanField(default=False, null=True, blank=True)


class Article(models.Model):
    user = models.ForeignKey(Compte, on_delete=models.RESTRICT, null=True, blank=True)
    titre = models.CharField(max_length=200, null=True, blank=True)
    image = models.ImageField(upload_to='./article', null=True, blank=True, validators=[valider_image])
    integration_code = models.TextField(null=True, blank=True)
    galery = models.ManyToManyField(to=Galery, related_name="Images_article")
    description = models.TextField(blank=True, null=True)
    mise_a_jour = models.DateTimeField(auto_now=True, null=True, blank=True)


class Config(models.Model):
    nom = models.CharField(max_length=500, null=True, blank=True)
    image_background = models.ImageField(upload_to="./", null=True, blank=True, validators=[valider_image])
    logo = models.ImageField(upload_to="./", null=True, blank=True, validators=[valider_image])
    slogant = models.CharField(max_length=500, null=True, blank=True)
    welcome_text = models.CharField(max_length=200, null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    adresse = models.TextField(null=True, blank=True)
    facebook = models.CharField(max_length=255, null=True, blank=True)
    twitter = models.CharField(max_length=255, null=True, blank=True)
    youtube = models.CharField(max_length=255, null=True, blank=True)
    gmail = models.EmailField(max_length=255, null=True, blank=True)
    instagram = models.CharField(max_length=255, null=True, blank=True)
    linkedin = models.CharField(max_length=255, null=True, blank=True)
    phone1 = models.CharField(max_length=20, null=True, blank=True)
    phone2 = models.CharField(max_length=20, null=True, blank=True)
    phone3 = models.CharField(max_length=20, null=True, blank=True)
    phone4 = models.CharField(max_length=20, null=True, blank=True)
    phone5 = models.CharField(max_length=20, null=True, blank=True)
    phone6 = models.CharField(max_length=20, null=True, blank=True)
    phone7 = models.CharField(max_length=20, null=True, blank=True)
    partenaire1 = models.CharField(max_length=255, null=True, blank=True)
    link1 = models.CharField(max_length=255, null=True, blank=True)
    partenaire2 = models.CharField(max_length=255, null=True, blank=True)
    link2 = models.CharField(max_length=255, null=True, blank=True)
    partenaire3 = models.CharField(max_length=255, null=True, blank=True)
    link3 = models.CharField(max_length=255, null=True, blank=True)
    partenaire4 = models.CharField(max_length=255, null=True, blank=True)
    link4 = models.CharField(max_length=255, null=True, blank=True)
    partenaire5 = models.CharField(max_length=255, null=True, blank=True)
    link5 = models.CharField(max_length=255, null=True, blank=True)
    partenaire6 = models.CharField(max_length=255, null=True, blank=True)
    link6 = models.CharField(max_length=255, null=True, blank=True)
    partenaire7 = models.CharField(max_length=255, null=True, blank=True)
    link7 = models.CharField(max_length=255, null=True, blank=True)


class Contact(models.Model):
    nom = models.CharField(max_length=100, null=True, blank=True)
    mail = models.EmailField(null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    raison = models.CharField(max_length=100, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    traiter = models.BooleanField(default=False, null=True, blank=True)
    mise_a_jour = models.DateTimeField(auto_now=True, null=True, blank=True)