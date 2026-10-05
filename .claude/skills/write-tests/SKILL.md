---
name: write-tests
description: Étape 2 du workflow TDD backend — écrit les tests pytest du plan validé et vérifie qu'ils échouent pour la bonne raison (phase rouge), sans toucher au code de production. À utiliser après /plan-tests dans CollabAnnotate_BackEnd.
---

# Écrire les tests (phase rouge)

Pré-requis : un plan de tests validé par l'utilisateur (commentaire sur l'issue, `gh issue view <n> --comments`) et la branche de l'issue active.

## 1. Écrire
- Respecter `.claude/rules/testing.md` : fonctions pytest, fixtures de `api/tests/conftest.py`, factories de `api/tests/factories.py`, matrice de droits paramétrée.
- Placer chaque test dans le fichier du domaine (`api/tests/test_<domaine>.py`) ; créer une factory manquante dans `factories.py` plutôt que de construire les objets à la main.
- Un test par ligne du plan, avec le même nom. Ne **pas** modifier le code de production à cette étape (sauf une factory ou une fixture de test).

## 2. Vérifier la phase rouge
```powershell
pytest api/tests/test_<domaine>.py -k "<motif>" -q
```
- Chaque nouveau test doit **échouer pour la raison attendue** (mauvais code HTTP, assertion métier), pas pour une erreur de syntaxe, d'import ou de fixture.
- Un test qui passe déjà : soit il protège une non-régression (le signaler), soit le test est faux (le corriger).
- `ruff check api/tests` doit passer.

## 3. Committer
```powershell
git add api/tests
git commit -m "test: <ce que les tests décrivent>" -m "Refs #<n>"
```

## 4. Rendre compte
Montrer à l'utilisateur le tableau « test → statut (rouge/vert) → raison de l'échec », expliquer ce que chaque test vérifie, puis enchaîner avec `/implement`.
