---
paths:
  - "api/**/*.py"
  - "backend/**/*.py"
---

# Conventions API (DRF)

- Les entrées sont validées par un **serializer**, jamais par des `request.data.get(...)` dispersés. Une vue fonction ou une `@action` a son serializer d'entrée.
- Ne jamais renvoyer `str(e)` au client : message générique + `logger.exception(...)`. Laisser DRF transformer les `ValidationError` / `PermissionDenied` / `NotFound`.
- Un query param invalide (`?project=abc`) donne **400**, jamais 500.
- Querysets : `select_related` / `prefetch_related` pour les relations lues par le serializer, `annotate(Count(...))` plutôt qu'un `.count()` par objet (N+1).
- Coordonnées échangées avec le front normalisées 0–1.
- Uploads : vérifier le contenu réel de l'image (Pillow), le type, la taille ; nom de fichier généré côté serveur.
- Le refresh token JWT ne sort **que** dans le cookie HttpOnly. L'access token seul est renvoyé en JSON.
- Un changement de format de réponse (champ renommé, pagination, valeurs de statut) casse le frontend : le signaler dans la PR et créer l'issue liée dans `CollabAnnotate/CollabAnnotate_FrontEnd`.
- Code sous ruff (`ruff check .`), lignes ≤ 120 caractères.
