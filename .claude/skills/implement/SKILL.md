---
name: implement
description: Étape 3 du workflow TDD backend — écrit le code minimal qui fait passer les tests rouges au vert, puis lance toute la suite, ruff et le contrôle des migrations. À utiliser après /write-tests dans CollabAnnotate_BackEnd (ou seul pour un changement trivial : docs, typo).
---

# Implémenter (phase verte)

## 1. Expliquer avant de coder (consigne d'apprentissage)
Présenter brièvement l'approche : quels fichiers changent, quel concept Django/DRF est utilisé (et son équivalent Symfony si utile), pourquoi ce choix plutôt qu'un autre.

## 2. Coder le minimum
- Faire passer les tests de l'issue **sans** élargir le périmètre (pas de refactor opportuniste : ouvrir une issue à la place).
- Respecter `.claude/rules/` : `permissions.md`, `api.md`, `models.md`.
- Changement de modèle → `python manage.py makemigrations` et relire la migration générée.

## 3. Boucle rouge → vert
```powershell
pytest api/tests/test_<domaine>.py -q        # les tests de l'issue
pytest -q                                    # toute la suite (--create-db si nouvelle migration)
ruff check .
python manage.py makemigrations --check --dry-run
```
Tout doit être vert. Ne jamais modifier un test pour le faire passer sans l'expliquer à l'utilisateur (un test faux se corrige, un test juste ne se contourne pas).

## 4. Committer
```powershell
git add -A
git commit -m "<feat|fix|refactor>: <description>" -m "Refs #<n>"
```
Vérifier avec `git status` qu'aucun fichier indésirable (`.env`, médias, `.pt`) n'est inclus.

## 5. Enchaîner
Résumer ce qui a changé, puis lancer `/review`.
