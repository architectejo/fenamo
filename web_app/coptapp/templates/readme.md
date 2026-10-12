# Guide d'implementation

### Actions

* [X] Authentification des utilisateurs
* [X] Deconnexion aux session
* [X] Ajout des utilisateurs de la troisième privilège(:super user, :utilisateur de la cinquième privilege)
* [X] attribution des rôles
* [X] Conception des models
* [X] Migration de la base des données
* [X] ajouter une province
* [X] ajouter une ville
* [X] Ajout d'une antenne
* [X] Ajout des membres(utilisateur de la première privilège)
* [X] Modifier un membre
* [X] Supprimer un membre
* [X] Ajout des motos
* [X] Supprimer moto
* [X] Modifier moto
* [X] Creation des notifications
* [X] Ajout des utilisateurs de la deuxième et la première privilege(utilisateur de la troisième privilège)
* [X] Ajout des visiteurs privilegés (utilisateur de la troisième privilège)
* [X] Mise en place des statistiques membres
* [X] Mise en place des statistiques motos
* [X] Generation des notifications ( utilisation de la fonction -> notify() )
* [X] Champ des recherches par nom ou numéro
* [X] Vue de la moto
* [X] Attribution d'une moto
* [X] Ajout d'une province
* [X] Affichage des notifications selon le privilège
* [X] Validation des membres
* [X] Modification des données d'authentification
* [X] Vue d'antenne
* [X] Page 404
* [X] Affichage des beneficiaires
* [X] Ajout des beneficiaires
* [X] Modification et suppression des beneficiaires
* [ ] Mise en place du système de communication et commentaires <--
* [X] Champ de recherche pour les visiteurs
* [X] Affichage des membres sans repetition
* [X] Administration du site
* [ ] Affichage de la liste d'utilisateur (Optionelle)
* [ ] Intégration de progréssive webApp

### Environement virtuel:
source /home/cp1711423p04/virtualenv/fenamo/3.10/bin/activate && cd /home/cp1711423p04/fenamo

### Models

___________________________________Configuration_______________________

##### Province _

* user (::null=True)
* nom

##### Ville _

* user (::null=True)
* province
* nom

##### Antenne _

* ville
* province
* zone_operationnelle
* nom

___________________________________________________Models démandés_______________________________________

##### Membre

* user
* info <- fiche de membre
* ville
* province
* is_delete

##### Motos

* user
* membre
* motar(membre.id)
* info <- fiche d'identification de la moto
* numero
* date_d_abonnement
* ville
* province
* antenne
* is_delete

##### Famille

* user
* membre
* numero_priorite
* nom_beneficière
* date_de naissance

##### Notification _

* user
* membre
* description
* is_valide

##### Communique _

* user(::privilège3 or admin)
* message

##### Reaction _

* user
* communique
* reaction
