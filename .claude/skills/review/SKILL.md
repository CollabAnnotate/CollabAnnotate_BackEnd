---
name: review
description: Étape 4 du workflow TDD backend — fait relire la branche par /code-review puis applique la checklist propre au dépôt (droits, sécurité, N+1, migrations, tests), présente les remarques et corrige après validation. À utiliser après /implement dans CollabAnnotate_BackEnd.
---

# Review de la branche

## 1. Revue automatique
Lancer le skill intégré `/code-review` sur le diff de la branche par rapport à `main` (`git diff main...HEAD`).

## 2. Checklist CollabAnnotate (vérifier chaque point sur le diff)
- [ ] **Droits** : tout nouveau queryset filtré par `visible_projects_q` ; écritures contrôlées par `has_project_role` ; aucun champ donnant des droits modifiable ; pas de `try/except Exception` autour de `get_object()`/`is_valid()`.
- [ ] **Sécurité** : pas de `str(e)` renvoyé, entrées validées par serializer, uploads vérifiés, refresh token jamais dans un corps de réponse, aucun secret en dur.
- [ ] **Données** : écritures multiples dans `transaction.atomic()`, migrations présentes et relues, coordonnées normalisées 0–1, `last_modified_by` renseigné.
- [ ] **Performance** : pas de N+1 (`select_related` / `annotate`), pas de requête dans une boucle.
- [ ] **Tests** : chaque critère d'acceptation de l'issue a son test ; matrice de droits présente ; YOLO mocké ; pas de test affaibli pour passer.
- [ ] **Contrat d'API** : un changement de format est signalé et une issue frontend liée existe.
- [ ] **Lisibilité** : code dans le style du fichier, pas de code mort ni de `print`.

## 3. ✋ Présenter et attendre la validation
Présenter les remarques classées (bloquant / à corriger / suggestion), chacune avec fichier:ligne et explication pédagogique. **S'arrêter** et attendre que l'utilisateur choisisse ce qu'on corrige.

## 4. Corriger
Pour chaque remarque retenue : test d'abord si c'est un bug, puis correctif. Relancer `pytest -q` et `ruff check .`, puis :
```powershell
git commit -am "fix: corrections de review" -m "Refs #<n>"
```
Enchaîner avec `/merge`.
