---
paths:
  - "api/views.py"
  - "api/views/**/*.py"
  - "api/permissions.py"
  - "api/serializers.py"
---

# Droits d'accès

- **Tout droit dérive du projet.** Utiliser `visible_projects_q(user, prefix)` dans chaque `get_queryset()` (ex. `prefix='dataset__project__'`, `'dataitem__dataset__project__'`) et `has_project_role(user, project, roles)` pour les écritures. Ne pas recoder ces règles dans une vue.
- Lecture : propriétaire, collaborateur ou projet publié. Écriture : selon `EDITOR_ROLES` / `ANNOTATOR_ROLES` de `api/permissions.py`. Suppression / publication : propriétaire seul.
- Un objet hors du périmètre visible doit renvoyer **404** (il est filtré par `get_queryset`), un objet visible mais non modifiable **403**.
- Les contrôles de **création** se font dans les `validate_<champ>` du serializer et lèvent `PermissionDenied`.
- **Jamais** de `try/except Exception` autour de `get_object()` ou `is_valid()` : les 403/404/400 deviendraient des 500.
- Le `role` global (`annotateur`/`verificateur`/`admin`) n'est jamais modifiable par l'utilisateur lui-même. Tout champ qui donne des droits (`role`, `project`, `invited_email`…) est en lecture seule après création.
- Les `ModelViewSet` n'exposent que les actions nécessaires (`http_method_names` ou mixins) : pas de `update` sur une ressource qui ne doit pas changer.
- Tout nouveau endpoint est couvert par une matrice de droits : propriétaire / éditeur / lecteur / étranger (voir `testing.md`).
