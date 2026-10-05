"""Hook SessionStart : rappelle à Claude où en est le travail (branche, issue, PR, CI).

Tout ce qui est imprimé sur stdout est ajouté au contexte de la session. En cas d'échec
(pas de réseau, gh absent), le hook reste silencieux.
"""
import json
import re
import subprocess
import sys


def run(*args):
    try:
        out = subprocess.run(list(args), capture_output=True, text=True, timeout=8, encoding="utf-8")
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def main():
    # Sous Windows, Python écrirait en cp1252 : Claude Code attend de l'UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    branch = run("git", "branch", "--show-current")
    if not branch:
        return
    lines = [f"Dépôt CollabAnnotate_BackEnd — branche courante : {branch}."]
    match = re.match(r"^\w+/(\d+)-", branch)
    if match:
        issue = run("gh", "issue", "view", match.group(1), "--json", "number,title,state")
        if issue:
            data = json.loads(issue)
            lines.append(f"Issue liée : #{data['number']} « {data['title']} » ({data['state']}).")
    pr = run("gh", "pr", "view", "--json", "number,url,statusCheckRollup")
    if pr:
        data = json.loads(pr)
        checks = {c.get("conclusion") or c.get("status") for c in data.get("statusCheckRollup") or []}
        lines.append(f"PR ouverte : #{data['number']} {data['url']} — CI : {', '.join(sorted(checks)) or 'aucune'}.")
    elif branch in ("main", "master"):
        lines.append("Sur main : démarrer une issue avec /plan-tests <n> (gh issue list --label P0).")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
