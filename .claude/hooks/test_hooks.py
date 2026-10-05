"""Tests des hooks Claude Code du dépôt (lancés par pytest avec le reste de la suite)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS))

import guard_bash  # noqa: E402
import guard_files  # noqa: E402


@pytest.fixture
def sur_branche(monkeypatch):
    def choisir(nom):
        monkeypatch.setattr(guard_bash, "current_branch", lambda cwd: nom)
    return choisir


@pytest.mark.parametrize("commande", [
    "git push origin main",
    "git push origin HEAD:main",
    "git push --force origin feat/3-invitations",
    "git push -f",
    'git commit --no-verify -m "wip"',
    "git add .env",
    "git add yolov8n.pt",
    "git add -f media/x.jpg",
    "git status && git push origin main",
    "gh pr merge 23",
    "gh pr merge 23 --merge",
])
def test_commandes_bloquees(commande, sur_branche):
    sur_branche("feat/3-invitations")
    assert guard_bash.check(commande) is not None


@pytest.mark.parametrize("commande", [
    "git push -u origin HEAD",
    "git push --force-with-lease",
    "git add api/tests .env.example",
    'git commit -m "fix: corrige le chargement du .env"',
    "gh pr merge 23 --squash --delete-branch",
    "pytest -q",
])
def test_commandes_autorisees_sur_une_branche_d_issue(commande, sur_branche):
    sur_branche("feat/3-invitations")
    assert guard_bash.check(commande) is None


@pytest.mark.parametrize("commande", ["git push", "git push -u origin HEAD", "git push origin"])
def test_pousser_depuis_main_est_bloque(commande, sur_branche):
    sur_branche("main")
    assert guard_bash.check(commande) is not None


@pytest.mark.parametrize("chemin, bloque", [
    (".env", True),
    ("backend/.env.local", True),
    (".env.example", False),
    ("api/views.py", False),
    ("api/migrations/0001_initial.py", True),          # publiée sur origin/main
    ("api/migrations/0099_nouvelle.py", False),        # nouvelle migration : autorisée
])
def test_guard_files(chemin, bloque):
    root = HOOKS.parents[1]
    assert (guard_files.check(str(root / chemin), cwd=root) is not None) is bloque


def test_le_hook_bloque_avec_le_code_2_et_un_message():
    payload = json.dumps({"tool_input": {"command": "git push origin main"}})
    result = subprocess.run([sys.executable, str(HOOKS / "guard_bash.py")], input=payload,
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 2
    assert "main" in result.stderr
