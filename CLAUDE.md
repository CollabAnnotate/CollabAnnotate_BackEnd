# CLAUDE.md — Backend CollabAnnotate

API Django 5.2 LTS + Django REST Framework + SimpleJWT, PostgreSQL 17 via Docker Compose, détection YOLOv8. Le frontend React vit dans un dépôt séparé (`../CollabAnnotate_FrontEnd`).

## Workflow de développement

Chaque changement part d'une **GitHub Issue** et suit les skills du dépôt, dans l'ordre :

1. `/plan-tests <n°issue>` — plan des cas de test, commenté sur l'issue (✋ validation de l'utilisateur)
2. `/write-tests` — tests écrits et **rouges** pour la bonne raison
3. `/implement` — code minimal jusqu'au vert, suite complète + ruff
4. `/review` — `/code-review` + checklist du dépôt (✋ validation)
5. `/merge` — PR, CI verte, squash-merge (✋ validation)

### Hooks et agents
- **Hooks**, écrits directement dans la section `hooks` de `.claude/settings.json` :
  - avant une commande Bash ou PowerShell : bloque le push sur `main`, `--force`, `--no-verify`, `git add` de `.env` / `.pt` / `media/` et un merge autrement qu'en squash ;
  - avant l'écriture d'un fichier : protège les `.env` ;
  - après l'écriture d'un fichier : passe ruff sur le fichier `.py` modifié ;
  - au démarrage d'une session : rappelle la branche et la PR ouverte.
- Le blocage de `git push` (sans argument) depuis `main` n'est pas couvert par le hook : il reste une règle de `.claude/rules/git.md`.
- **Agents de review** (lecture seule, lancés par `/review`) : `security-reviewer` et `test-reviewer`.
- Ils ne s'appliquent que si Claude Code est lancé **depuis ce dossier**.

Branches : `feat/<n>-slug`, `fix/<n>-slug`, `chore/<n>-slug` depuis `main`. Commits en Conventional Commits, messages en français. Ne jamais pousser sur `main` directement ni merger sans accord explicite.

## Commandes (Windows / PowerShell)

```powershell
python -m venv venv; venv\Scripts\activate
pip install -r requirements-dev.txt
Copy-Item .env.example .env        # puis remplir SECRET_KEY / mots de passe
docker compose up -d               # PostgreSQL 17 (lit .env)
python manage.py migrate
python manage.py runserver         # http://localhost:8000

pytest                                         # tous les tests (base réutilisée : --reuse-db)
pytest --create-db                             # après une nouvelle migration
pytest api/tests/test_auth.py -k cookie        # un fichier / un filtre
pytest --cov                                   # couverture
ruff check .                                   # lint (--fix pour corriger)
python manage.py makemigrations --check --dry-run
```

- Les tests ont besoin de PostgreSQL démarré (pytest-django crée `test_<nom>`).
- Toute la config sensible (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL`, `CORS_ALLOWED_ORIGINS`, `JWT_COOKIE_SECURE`) vient de `.env` via `django-environ` ; les `POSTGRES_*` du même `.env` alimentent `docker-compose.yml` et doivent rester cohérentes avec `DATABASE_URL`.
- Le modèle YOLO (`yolov8n.pt`, non versionné, téléchargé par ultralytics) est chargé à la demande par `get_model()` dans `api/views.py` (`lru_cache`) ; ne pas réintroduire de chargement au niveau module (torch est lourd). Dans les tests il est **toujours mocké** (`yolo_mock` dans `api/tests/conftest.py`).

## Tests

- `api/tests/` : un fichier par domaine (`test_auth`, `test_projects`, `test_annotations`, `test_collaboration`, `test_users`, `test_detection`).
- Nouveaux tests en style pytest (fonctions + fixtures) avec les factories de `api/tests/factories.py`. Les classes `APITestCase` existantes restent valides.
- Fixtures de `conftest.py` : `api_client`, `user`, `auth_client`, `project`, `yolo_mock` (autouse), `MEDIA_ROOT` temporaire (autouse).
- Les vues du router se nomment `<basename>-list` / `<basename>-detail` (ex. `reverse('project-list')`).

## Architecture

Tout le code métier est dans l'app unique **`api/`** :
- `models.py` — utilisateur custom `api.User` (`AUTH_USER_MODEL`) avec un `role` global `annotateur` / `verificateur` / `admin`. Hiérarchie : `Project` → `Dataset` → `DataItem` (image) → `Annotation` (bbox `x_min/y_min/x_max/y_max` **normalisées 0–1**).
- `Annotation.save()` écrit automatiquement une entrée `AnnotationHistory` (création, ou mise à jour si label/coordonnées changent, via `last_modified_by`). Renseigner `last_modified_by` avant un `save()` de mise à jour.
- Validation : `is_validated`, `validation_status` (`validé`/`rejeté`), `validated_by`, `validated_at` sur `Annotation`, via `validate_annotation`.
- Collaboration par projet : `ProjectCollaborator` avec un **second système de rôles** (`viewer`/`annotator`/`editor`/`admin`) et `ProjectInvitation`.
- Le `role` global est **en lecture seule** dans `UserSerializer` (inscription = `annotateur`) ; il ne se modifie que via l'admin Django ou le back-office `admin/users/` (`IsRoleAdmin`).
- Droits : centralisés dans `api/permissions.py`, dérivés du **projet**. `visible_projects_q(user, prefix)` filtre les `get_queryset` ; `has_project_role(user, project, roles)` décide des écritures. Les contrôles de **création** sont dans les `validate_<champ>` des serializers (lèvent `PermissionDenied`).
- Compteurs de projet annotés en SQL dans `ProjectViewSet.get_queryset` ; `stats/` alimente l'écran Rapports.
- `views.py` mélange `ModelViewSet` (router de `api/urls.py`, `@action` custom) et vues fonctions `@api_view`.
- Auth : JWT sur toute l'API (`IsAuthenticated` global), seul `register/` est `AllowAny`. Access token de 15 min en JSON ; **le refresh token ne transite que par un cookie HttpOnly** (`JWT_REFRESH_COOKIE`). `CookieTokenRefreshView` le fait tourner (blacklist), `LogoutView` le révoque. Ne jamais remettre le refresh token dans un corps de réponse.
- Routes sous `/api/` ; médias sous `/media/`.

Les règles détaillées sont dans `.claude/rules/` (chargées selon les fichiers touchés).
