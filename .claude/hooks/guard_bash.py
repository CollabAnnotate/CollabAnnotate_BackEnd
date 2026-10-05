"""Hook PreToolUse (Bash / PowerShell) : bloque les commandes git / gh contraires au workflow.

Entrée : JSON du hook sur stdin ({"tool_input": {"command": ...}, "cwd": ...}).
Sortie : exit 0 = autorisé ; exit 2 = bloqué, le message sur stderr est renvoyé à Claude.
"""
import json
import re
import subprocess
import sys

PROTECTED_BRANCHES = ("main", "master")
# Fichiers à ne jamais committer (.env.example reste autorisé)
FORBIDDEN_PATHS = re.compile(r"(^|[\s/\\])(\.env(?!\.example)\S*|\S+\.pt|media[/\\]\S*|media(?=\s|$))")


def current_branch(cwd):
    try:
        out = subprocess.run(["git", "branch", "--show-current"], cwd=cwd, capture_output=True,
                             text=True, timeout=5)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def check(command, cwd=None):
    """Renvoie le motif du refus, ou None si la commande est autorisée."""
    for part in re.split(r"&&|\|\||;|\n", command):
        part = part.strip()
        words = part.split()
        if len(words) < 2:
            continue

        if words[0] == "git" and "--no-verify" in words:
            return "`--no-verify` contourne les vérifications : corriger le problème plutôt que de l'ignorer."

        if words[:2] == ["git", "push"]:
            if "--force" in words or "-f" in words:
                return "`git push --force` est interdit ; utiliser `--force-with-lease` sur sa propre branche."
            # git push [options] [remote] [refspec…] : la cible est la partie droite de chaque refspec
            args = [w for w in words[2:] if not w.startswith("-")]
            refspecs = args[1:]
            if not refspecs or any(r.split(":")[-1] == "HEAD" for r in refspecs):
                refspecs = refspecs + [current_branch(cwd)]
            if any(r.split(":")[-1] in PROTECTED_BRANCHES for r in refspecs):
                return "Pousser sur `main` est interdit : passer par une branche d'issue et une PR (skill /merge)."

        if words[:2] == ["git", "add"]:
            if "-f" in words or "--force" in words:
                return "`git add --force` contourne le .gitignore : ne pas versionner ce fichier."
            if FORBIDDEN_PATHS.search(" " + " ".join(words[2:])):
                return "Fichier interdit dans git (.env, poids .pt, media/) : il doit rester local."

        if words[:3] == ["gh", "pr", "merge"] and "--squash" not in words:
            return ("Les PR se mergent en squash : `gh pr merge --squash --delete-branch`, "
                    "après accord de l'utilisateur.")
    return None


def main():
    # Sous Windows, Python écrirait en cp1252 : Claude Code attend de l'UTF-8
    sys.stderr.reconfigure(encoding="utf-8")
    payload = json.load(sys.stdin)
    command = (payload.get("tool_input") or {}).get("command", "")
    reason = check(command, payload.get("cwd"))
    if reason:
        print(f"Commande bloquée par le hook guard_bash : {reason}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
