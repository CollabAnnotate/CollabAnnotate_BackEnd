"""Hook PreToolUse (Edit / Write) : protège les secrets et les migrations déjà publiées.

- `.env` (mais pas `.env.example`) : jamais lu ni écrit par Claude.
- Une migration présente sur `origin/main` est appliquée chez tout le monde : on en crée
  une nouvelle (`makemigrations`), on ne la modifie pas.
"""
import json
import subprocess
import sys
from pathlib import Path


def is_published_migration(path, cwd):
    if "migrations" not in path.parts or path.suffix != ".py" or path.name == "__init__.py":
        return False
    try:
        root = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True,
                              text=True, timeout=5).stdout.strip()
        relative = path.resolve().relative_to(Path(root).resolve()).as_posix()
        found = subprocess.run(["git", "cat-file", "-e", f"origin/main:{relative}"], cwd=cwd,
                               capture_output=True, timeout=5)
        return found.returncode == 0
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def check(file_path, cwd=None):
    path = Path(file_path)
    if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
        return "les fichiers .env contiennent des secrets : les modifier à la main, pas via Claude."
    if is_published_migration(path, cwd):
        return ("cette migration est déjà sur main : créer une nouvelle migration "
                "(python manage.py makemigrations) au lieu de la modifier.")
    return None


def main():
    # Sous Windows, Python écrirait en cp1252 : Claude Code attend de l'UTF-8
    sys.stderr.reconfigure(encoding="utf-8")
    payload = json.load(sys.stdin)
    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    reason = check(file_path, payload.get("cwd")) if file_path else None
    if reason:
        print(f"Écriture bloquée par le hook guard_files : {reason}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
