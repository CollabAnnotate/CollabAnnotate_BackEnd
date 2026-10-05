## Résumé
<!-- Ce que change cette PR et pourquoi -->

Closes #

## Plan de tests
<!-- Cas couverts : nominal, erreurs, droits (propriétaire / éditeur / lecteur / étranger), limites -->
- [ ]

## Checklist
- [ ] Tests écrits avant le code (rouges, puis verts)
- [ ] `pytest` et `ruff check .` passent en local
- [ ] Migrations générées (`makemigrations --check`)
- [ ] Droits vérifiés via `api/permissions.py` (pas de `try/except Exception` autour de `get_object()`)
- [ ] Contrat d'API inchangé, ou issue frontend liée
