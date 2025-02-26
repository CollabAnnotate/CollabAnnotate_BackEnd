# CollabAnnotate Backend

Une application backend robuste pour la plateforme collaborative d'annotation d'images CollabAnnotate.

## 🚀 Technologies utilisées

- Django 
- Django REST Framework
- PostgreSQL
- JWT Authentication

## 📋 Prérequis

- Python 3.8+
- pip
- PostgreSQL

## 🛠 Installation

1. Cloner le repository
```bash
git clone https://github.com/votre-username/CollabAnnotate_BackEnd.git
cd CollabAnnotate_BackEnd
```

2. Créer un environnement virtuel
```bash
python -m venv venv
source venv/bin/activate  # Sur Windows: venv\Scripts\activate
```

3. Installer les dépendances
```bash
pip install -r requirements.txt
```

4. Configurer les variables d'environnement
Créer un fichier `.env` à la racine du projet avec :
```
DEBUG=True
SECRET_KEY=votre_clé_secrète
DB_NAME=votre_db_name
DB_USER=votre_db_user
DB_PASSWORD=votre_db_password
DB_HOST=localhost
```

5. Appliquer les migrations

'''bash
python manage.py makemigrations
''' 

```bash
python manage.py migrate
```

6. Lancer le serveur de développement
```bash
python manage.py runserver
```

## 🌟 Fonctionnalités principales

- **Gestion des projets** : Création et gestion de projets d'annotation
- **Système de rôles** : Annotateur, Vérificateur, Administrateur
- **Annotations collaboratives** : Système de validation et historique des modifications
- **API REST** : Endpoints sécurisés avec JWT
- **Détection automatique** : Intégration avec des modèles de détection d'objets

## 📚 Documentation API

### Authentification
- POST `/api/token/` : Obtenir un token JWT
- POST `/api/token/refresh/` : Rafraîchir un token JWT

### Projets
- GET `/api/projects/` : Liste des projets
- POST `/api/projects/` : Créer un projet
- GET `/api/projects/{id}/` : Détails d'un projet
- PUT `/api/projects/{id}/` : Modifier un projet
- DELETE `/api/projects/{id}/` : Supprimer un projet

### Annotations
- GET `/api/annotations/` : Liste des annotations
- POST `/api/annotations/` : Créer une annotation
- GET `/api/annotations/{id}/` : Détails d'une annotation
- PUT `/api/annotations/{id}/` : Modifier une annotation
- DELETE `/api/annotations/{id}/` : Supprimer une annotation


