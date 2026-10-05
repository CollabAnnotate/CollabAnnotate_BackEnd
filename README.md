# CollabAnnotate Backend

Une application backend robuste pour la plateforme collaborative d'annotation d'images CollabAnnotate.

## 🚀 Technologies utilisées

- Django 5.2 LTS
- Django REST Framework
- PostgreSQL 17 (via Docker Compose)
- JWT Authentication (SimpleJWT)
- YOLOv8 (ultralytics) pour la détection d'objets

## 📋 Prérequis

- Python 3.12+
- pip
- Docker (pour PostgreSQL)

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
Copier `.env.example` en `.env`, puis remplacer les valeurs `a-remplacer` (`SECRET_KEY`, `POSTGRES_PASSWORD` et le mot de passe dans `DATABASE_URL`) :
```bash
cp .env.example .env
```

5. Démarrer PostgreSQL
```bash
docker compose up -d
```

6. Appliquer les migrations
```bash
python manage.py migrate
```

7. Lancer le serveur de développement
```bash
python manage.py runserver
```

Lancer les tests : `python manage.py test api`.

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


