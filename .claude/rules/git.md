# Git et GitHub

- Dépôt GitHub : `CollabAnnotate/CollabAnnotate_BackEnd`, branche par défaut `main`. Le frontend est un dépôt séparé (`CollabAnnotate/CollabAnnotate_FrontEnd`).
- Une branche par issue, créée depuis `main` à jour : `feat/<n>-slug`, `fix/<n>-slug`, `chore/<n>-slug`, `test/<n>-slug`.
- Commits en **Conventional Commits**, description en français : `test: …`, `feat: …`, `fix: …`, `refactor: …`, `chore: …`, `docs: …`. Référencer l'issue dans le corps (`Refs #12`).
- Ordre attendu dans une PR : commit(s) `test:` (rouges) puis `feat:`/`fix:` (verts), puis corrections de review.
- La PR utilise `.github/pull_request_template.md` et contient `Closes #<n>`. Merge en **squash** uniquement après CI verte **et** accord explicite de l'utilisateur.
- Ne jamais : pousser sur `main`, `--force` sur une branche partagée, `--no-verify`, committer `.env`, des poids `.pt` ou des médias.
