---
paths:
  - "api/tests/**/*.py"
---

# Tests (pytest-django)

- Nouveaux tests en **fonctions pytest** + fixtures de `api/tests/conftest.py` (`api_client`, `user`, `auth_client`, `project`) et factories de `api/tests/factories.py`. Pas de nouvelle classe `APITestCase`.
- Marquer l'accès base : `pytestmark = pytest.mark.django_db` en tête de fichier (ou fixture `db`).
- Nommage en français, qui décrit le comportement : `test_etranger_ne_peut_pas_accepter_l_invitation`.
- Un test = un comportement. Vérifier le code HTTP **et** l'état en base (`refresh_from_db()`), pas seulement la réponse.
- **Matrice de droits** paramétrée pour tout endpoint d'écriture :

  ```python
  @pytest.mark.parametrize("role, attendu", [
      ("owner", 200), ("editor", 200), ("viewer", 403), ("stranger", 404),
  ])
  ```

- Cas à couvrir systématiquement : nominal, entrée invalide (400), non authentifié (401), droits (403/404), limites (valeurs extrêmes, listes vides, doublons).
- Un bug corrigé = un test de non-régression qui échouait avant le correctif.
- YOLO est mocké par la fixture autouse `yolo_mock` : fixer `yolo_mock.return_value` pour simuler des détections. Ne jamais charger le vrai modèle dans un test.
- Images générées en mémoire avec Pillow (`Image.new(...)` + `SimpleUploadedFile`), pas de fichiers de fixture. `MEDIA_ROOT` est temporaire.
- Requêtes : verrouiller les corrections de N+1 avec `django_assert_num_queries`.
