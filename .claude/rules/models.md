---
paths:
  - "api/models.py"
  - "api/migrations/**/*.py"
---

# Modèles et migrations

- Choix : `models.TextChoices` avec des **valeurs ASCII en anglais** (`pending`, `accepted`) et des libellés français. Pas de nouvelles valeurs accentuées stockées en base.
- FK vers l'utilisateur : `on_delete=models.SET_NULL` (+ `null=True`) ou `PROTECT` pour ne pas effacer le travail partagé ; `CASCADE` seulement pour les données qui appartiennent vraiment à l'utilisateur.
- Invariants en base quand c'est possible : `CheckConstraint` (coordonnées 0 ≤ min < max ≤ 1), `UniqueConstraint`, index (`Meta.indexes`) sur les champs filtrés.
- Coordonnées des boxes toujours **normalisées 0–1**.
- `Annotation.save()` écrit l'historique : renseigner `last_modified_by` avant une mise à jour ; les écritures multiples passent par `transaction.atomic()`.
- Chaque changement de modèle s'accompagne de sa migration (`python manage.py makemigrations`), relue avant commit. Une migration de données utilise `apps.get_model()`, jamais l'import direct du modèle.
- Ajouter un `__str__` aux nouveaux modèles.
