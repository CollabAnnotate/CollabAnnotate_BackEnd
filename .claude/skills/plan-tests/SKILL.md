---
name: plan-tests
description: Étape 1 du workflow TDD backend — lit une GitHub Issue et le code concerné, puis produit le plan des cas de test (nominal, erreurs, droits, limites) à faire valider avant d'écrire le moindre test. À utiliser au démarrage de toute issue du dépôt CollabAnnotate_BackEnd.
argument-hint: <numéro d'issue>
---

# Planifier les tests d'une issue (backend)

Issue : `$ARGUMENTS`

## 1. Comprendre le besoin
1. `gh issue view $ARGUMENTS --comments` : lire le problème et les critères d'acceptation.
2. Lire le code concerné (vues, serializers, permissions, modèles) et les tests existants du domaine dans `api/tests/`. Repérer les fixtures / factories réutilisables.
3. Si le comportement attendu est ambigu, poser la question à l'utilisateur **avant** de planifier.

## 2. Préparer la branche
```powershell
git switch main; git pull
git switch -c <type>/$ARGUMENTS-<slug-court>   # type : feat | fix | chore | test
```

## 3. Rédiger le plan
Lister les cas sous forme de tableau, regroupés par catégorie, en respectant `.claude/rules/testing.md` :

| # | Fichier de test | Nom du test | Situation | Résultat attendu |
|---|---|---|---|---|

Catégories à passer en revue systématiquement :
- **Nominal** : le comportement demandé par l'issue.
- **Droits** : propriétaire / éditeur / annotateur / lecteur / étranger / non authentifié (401) → 200/403/404 selon `.claude/rules/permissions.md`.
- **Entrées invalides** : champs manquants, types faux, valeurs hors bornes → 400 (jamais 500).
- **Limites** : listes vides, doublons, coordonnées à 0 ou 1, objets d'un autre projet.
- **Non-régression** : pour un bug, le scénario exact qui le reproduit.
- **Effets de bord** : historique, notifications, compteurs, transactions (rien de partiel en cas d'erreur).

Indiquer pour chaque cas **pourquoi il échouera aujourd'hui** (ou s'il passe déjà : il protège contre une régression).

## 4. Expliquer (consigne d'apprentissage)
Avant le plan, expliquer en quelques lignes les concepts en jeu (ex. permissions DRF, transactions, contraintes), avec un parallèle Symfony quand c'est utile (Voters, Validator, Doctrine…).

## 5. Publier et ✋ attendre la validation
1. Poster le plan en commentaire : `gh issue comment $ARGUMENTS --body-file <fichier>` (fichier dans le scratchpad).
2. Présenter le plan à l'utilisateur et **s'arrêter** : ne rien écrire tant qu'il n'a pas validé ou amendé le plan.
3. Une fois validé : enchaîner avec `/write-tests`.
