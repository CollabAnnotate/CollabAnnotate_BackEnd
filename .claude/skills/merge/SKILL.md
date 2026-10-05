---
name: merge
description: Étape 5 du workflow TDD backend — pousse la branche, ouvre la PR (template, plan de tests, Closes #n), attend la CI GitHub Actions et squash-merge dans main uniquement après accord explicite de l'utilisateur. Dépôt CollabAnnotate_BackEnd.
disable-model-invocation: true
---

# Ouvrir la PR et merger

## 1. Vérifications locales
```powershell
git status                      # rien d'oublié, rien d'indésirable
pytest -q; ruff check .
git fetch origin; git rebase origin/main   # si main a avancé, puis relancer les tests
```

## 2. Pousser et ouvrir la PR
```powershell
git push -u origin HEAD
gh pr create --base main --title "<type>: <titre de l'issue>" --body-file <fichier>
```
Le corps suit `.github/pull_request_template.md` : résumé, `Closes #<n>`, plan de tests (cases cochées), checklist, et la mention « ⚠️ Contrat d'API modifié » + lien vers l'issue frontend si besoin. Terminer par :

🤖 Generated with [Claude Code](https://claude.com/claude-code)

## 3. Attendre la CI
```powershell
gh pr checks --watch
```
Si la CI échoue : lire le log (`gh run view --log-failed`), corriger sur la branche, re-pousser. Ne jamais contourner la CI.

## 4. ✋ Demander l'accord de merge
Donner à l'utilisateur le lien de la PR, l'état de la CI et le résumé des commits. **Ne merger qu'après un « oui » explicite.**

## 5. Merger et nettoyer
```powershell
gh pr merge --squash --delete-branch
git switch main; git pull; git fetch --prune
```
Vérifier que l'issue est fermée (`gh issue view <n>`), puis proposer la prochaine issue prioritaire (`gh issue list --label P0`).
