"""Hook PostToolUse (Edit / Write) : passe ruff sur le fichier Python modifié.

Corrige automatiquement ce qui peut l'être (imports, espaces) et renvoie à Claude les
erreurs restantes (exit 2) pour qu'il les corrige tout de suite, avant la CI.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENV_PYTHON = ROOT / "venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    VENV_PYTHON = ROOT / "venv" / "bin" / "python"


def main():
    # Sous Windows, Python écrirait en cp1252 : Claude Code attend de l'UTF-8
    sys.stderr.reconfigure(encoding="utf-8")
    payload = json.load(sys.stdin)
    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if not file_path.endswith(".py") or "migrations" in Path(file_path).parts:
        return
    if not VENV_PYTHON.exists():
        return  # pas de venv : la CI fera la vérification
    result = subprocess.run(
        [str(VENV_PYTHON), "-m", "ruff", "check", "--fix", "--quiet", "--output-format", "concise", file_path],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0 and result.stdout.strip():
        print(f"ruff signale des erreurs à corriger :\n{result.stdout.strip()}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
