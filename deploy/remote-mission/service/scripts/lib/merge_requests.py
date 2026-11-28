"""Merge request de la branche d'une conversation, ouverte par le service quand le travail est prêt.

Section merge_requests de la configuration. Le service frontal (jamais le pod de session ni l'agent)
ouvre la merge request de openwebui/<conversation> vers la branche cible :

    fin       : à « /fin », une fois le dernier push fait ;
    workflow  : quand toutes les étapes des workflows de la mission sont validées (ou sautées).

Une merge request déjà ouverte pour la branche est reprise, jamais doublée. La fusion reste faite par
une personne dans GitLab.

Jeton : celui de l'utilisateur, obtenu par Open WebUI à sa connexion GitLab (OIDC, portée api) et
transmis par le pipe avec son message ; la merge request est ouverte en son nom, avec ses droits. Il ne
sert qu'à cet appel : ni gardé, ni passé au pod de session ou à l'agent. À défaut, le jeton de
merge_requests.token_env (défaut GITLAB_MR_TOKEN), donné au seul service frontal et retiré de
l'environnement de l'agent.
"""

import json
import os
import urllib.error
import urllib.request
from urllib.parse import quote, urlencode

import access

DONE = {"validee", "sautee"}
TOKEN_ENV = "GITLAB_MR_TOKEN"


def token_env(config: dict) -> str | None:
    section = config.get("merge_requests")
    return section.get("token_env", TOKEN_ENV) if section else None


def reason(config: dict, report: dict) -> str | None:
    """Pourquoi ouvrir la merge request après ce tour, ou None."""
    section = config.get("merge_requests")
    if not section or report.get("errors") or not report.get("branch"):
        return None
    on = section.get("on", ["fin", "workflow"])
    if "fin" in on and report.get("mode") == "fin" and report.get("pushed"):
        return "fin de session"
    flows = report.get("workflows") or []
    if "workflow" in on and report.get("mode") == "agent" and flows \
            and all(f.get("stages") and set(f["stages"].values()) <= DONE for f in flows):
        return "workflow terminé"
    return None


def _call(method: str, url: str, token: str, payload: dict | None = None) -> tuple[int, object]:
    request = urllib.request.Request(url, method=method, data=json.dumps(payload).encode("utf-8") if payload else None,
                                     headers={"PRIVATE-TOKEN": token, "Accept": "application/json",
                                              "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read() or b"null")
        except ValueError:
            body = None
        return error.code, body


def open_for(config: dict, name: str, report: dict, why: str, user_token: str = "") -> dict:
    """Ouvre (ou retrouve) la merge request de la branche du tour. Lève RuntimeError en cas d'échec."""
    section = config["merge_requests"]
    env = section.get("token_env", TOKEN_ENV)
    token = user_token or os.environ.get(env, "")
    if not token:
        raise RuntimeError("aucun jeton GitLab : connexion à Open WebUI sans jeton de portée api "
                           f"(OAUTH_SCOPES) et variable {env} vide")
    api = (section.get("api") or config.get("access", {}).get("api", "")).rstrip("/")
    if not api:
        raise RuntimeError("merge_requests.api (ou access.api) manquant : API GitLab inconnue")
    mission = config["missions"][name]
    project = f"{api}/projects/{quote(access.project_of(mission), safe='')}"
    branch = report["branch"]
    code, found = _call("GET", f"{project}/merge_requests?" + urlencode({"state": "opened", "source_branch": branch}),
                        token)
    if code != 200:
        raise RuntimeError(f"GitLab : recherche des merge requests, code {code}")
    if found:
        return {"url": found[0].get("web_url"), "iid": found[0].get("iid"), "created": False, "reason": why}
    target = section.get("target") or mission.get("base")
    if not target:
        code, info = _call("GET", project, token)
        if code != 200 or not isinstance(info, dict) or not info.get("default_branch"):
            raise RuntimeError(f"GitLab : branche par défaut du projet illisible, code {code}")
        target = info["default_branch"]
    gate = report.get("gate") or {}
    lines = [f"Travail de la conversation Open WebUI `{report.get('chat')}` sur la mission « {name} » ({why}).", "",
             f"- Ouverte pour : {report.get('user') or 'utilisateur inconnu'}",
             f"- Dernier commit : {report.get('commit') or '-'}"]
    for flow in report.get("workflows") or []:
        stages = flow.get("stages") or {}
        done = sum(1 for v in stages.values() if v in DONE)
        lines.append(f"- Workflow {flow.get('workflow')} : {done}/{len(stages)} étapes validées ou sautées")
    if gate:
        lines.append(f"- En revue : {', '.join(gate.get('stages', []))}")
    lines += ["", "Ouverte par le service des missions à distance ; la fusion se décide ici."]
    payload = {"source_branch": branch, "target_branch": target, "remove_source_branch": False,
               "title": ("Draft: " if section.get("draft") else "") + f"Mission {name} : {report.get('chat')}",
               "description": "\n".join(lines)}
    if section.get("labels"):
        payload["labels"] = ",".join(section["labels"])
    code, created = _call("POST", f"{project}/merge_requests", token, payload)
    if code not in (200, 201) or not isinstance(created, dict):
        detail = created.get("message") if isinstance(created, dict) else None
        raise RuntimeError(f"GitLab : merge request refusée, code {code}" + (f" ({detail})" if detail else ""))
    return {"url": created.get("web_url"), "iid": created.get("iid"), "created": True, "reason": why}


def after_turn(config: dict, name: str, report: dict, emit=lambda kind, text: None, user_token: str = "") -> None:
    """Ajoute report["merge_request"] quand le tour rend le travail prêt ; un échec devient un avertissement."""
    why = reason(config, report)
    if not why:
        return
    emit("git", f"merge request ({why})")
    try:
        report["merge_request"] = open_for(config, name, report, why, user_token)
    except (RuntimeError, OSError, ValueError) as error:
        report["warnings"].append(f"merge request non ouverte : {error}")
