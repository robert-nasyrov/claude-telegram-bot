"""
DevOps tools for Claude Tool Use.
Allows managing Railway, GitHub, and Vercel from Telegram.
No computer needed — all API calls go directly from Railway.
"""

import json
import logging

import httpx

import config

logger = logging.getLogger(__name__)


# ──────────────────── Tool Definitions ────────────────

DEVOPS_TOOLS = [
    # === GitHub ===
    {
        "name": "github_list_repos",
        "description": "List user's GitHub repositories. Use when user asks about their repos or code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sort": {
                    "type": "string",
                    "enum": ["updated", "created", "pushed"],
                    "default": "updated",
                },
                "limit": {"type": "integer", "default": 15},
            },
            "required": [],
        },
    },
    {
        "name": "github_get_repo",
        "description": "Get details about a specific repo — branches, recent commits, files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repo name (without owner), e.g. 'claude-telegram-bot'",
                },
            },
            "required": ["repo"],
        },
    },
    {
        "name": "github_get_file",
        "description": (
            "Read a file from a GitHub repo. Use when user asks to see code, "
            "config files, or any file content from their repos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repo name"},
                "path": {"type": "string", "description": "File path, e.g. 'main.py' or 'src/config.py'"},
                "branch": {"type": "string", "default": "main"},
            },
            "required": ["repo", "path"],
        },
    },
    {
        "name": "github_list_commits",
        "description": "Get recent commits for a repo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["repo"],
        },
    },
    # === Railway ===
    {
        "name": "railway_list_projects",
        "description": (
            "List all Railway projects with their services and deployment status. "
            "Use when user asks about their deployments, infrastructure, or Railway projects."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "railway_get_deployments",
        "description": "Get recent deployments for a Railway service. Shows status, logs preview.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Railway project ID"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "railway_get_variables",
        "description": "Get environment variables for a Railway service (values are masked for security).",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "service_id": {"type": "string"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "railway_redeploy",
        "description": "Trigger a redeployment of a Railway service.",
        "input_schema": {
            "type": "object",
            "properties": {
                "deployment_id": {"type": "string", "description": "ID of the latest deployment to redeploy"},
            },
            "required": ["deployment_id"],
        },
    },
    {
        "name": "railway_get_logs",
        "description": "Get recent logs from a Railway deployment. Essential for debugging crashes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "deployment_id": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["deployment_id"],
        },
    },
    # === Vercel ===
    {
        "name": "vercel_list_projects",
        "description": "List Vercel projects and their deployment status.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "vercel_get_deployments",
        "description": "Get recent deployments for a Vercel project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["project_id"],
        },
    },
]


# ──────────────────── API Clients ─────────────────────

async def _github_request(method: str, path: str, params: dict = None) -> dict | list | None:
    url = f"https://api.github.com{path}"
    headers = {
        "Authorization": f"token {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(method, url, headers=headers, params=params)
        if resp.status_code >= 400:
            return {"error": f"GitHub API {resp.status_code}: {resp.text[:300]}"}
        return resp.json()


async def _railway_gql(query: str, variables: dict = None) -> dict:
    url = "https://backboard.railway.app/graphql/v2"
    headers = {
        "Authorization": f"Bearer {config.RAILWAY_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            return {"error": f"Railway API {resp.status_code}: {resp.text[:300]}"}
        data = resp.json()
        if data.get("errors"):
            return {"error": str(data["errors"][0].get("message", data["errors"]))}
        return data.get("data", data)


async def _vercel_request(method: str, path: str, params: dict = None) -> dict | list | None:
    url = f"https://api.vercel.com{path}"
    headers = {"Authorization": f"Bearer {config.VERCEL_TOKEN}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(method, url, headers=headers, params=params)
        if resp.status_code >= 400:
            return {"error": f"Vercel API {resp.status_code}: {resp.text[:300]}"}
        return resp.json()


# ──────────────────── Tool Executors ──────────────────

async def execute_tool(tool_name: str, tool_input: dict) -> str:
    try:
        # GitHub
        if tool_name == "github_list_repos":
            return await _gh_list_repos(tool_input)
        elif tool_name == "github_get_repo":
            return await _gh_get_repo(tool_input)
        elif tool_name == "github_get_file":
            return await _gh_get_file(tool_input)
        elif tool_name == "github_list_commits":
            return await _gh_list_commits(tool_input)
        # Railway
        elif tool_name == "railway_list_projects":
            return await _rw_list_projects(tool_input)
        elif tool_name == "railway_get_deployments":
            return await _rw_get_deployments(tool_input)
        elif tool_name == "railway_get_variables":
            return await _rw_get_variables(tool_input)
        elif tool_name == "railway_redeploy":
            return await _rw_redeploy(tool_input)
        elif tool_name == "railway_get_logs":
            return await _rw_get_logs(tool_input)
        # Vercel
        elif tool_name == "vercel_list_projects":
            return await _vc_list_projects(tool_input)
        elif tool_name == "vercel_get_deployments":
            return await _vc_get_deployments(tool_input)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
    except Exception as e:
        logger.error(f"DevOps tool error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


# ──── GitHub implementations ────

async def _gh_list_repos(params: dict) -> str:
    owner = config.GITHUB_OWNER
    result = await _github_request("GET", f"/users/{owner}/repos", params={
        "sort": params.get("sort", "updated"),
        "per_page": params.get("limit", 15),
    })
    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)
    summary = [{
        "name": r["name"],
        "private": r["private"],
        "language": r["language"],
        "updated_at": r["updated_at"],
        "description": r.get("description", ""),
    } for r in (result if isinstance(result, list) else [])]
    return json.dumps(summary, ensure_ascii=False, default=str)


async def _gh_get_repo(params: dict) -> str:
    owner = config.GITHUB_OWNER
    repo = params["repo"]
    # Get repo info + recent commits + file tree
    info = await _github_request("GET", f"/repos/{owner}/{repo}")
    if isinstance(info, dict) and "error" in info:
        return json.dumps(info)

    commits = await _github_request("GET", f"/repos/{owner}/{repo}/commits", params={"per_page": 5})
    tree = await _github_request("GET", f"/repos/{owner}/{repo}/contents/")

    summary = {
        "name": info.get("name"),
        "private": info.get("private"),
        "language": info.get("language"),
        "default_branch": info.get("default_branch"),
        "updated_at": info.get("updated_at"),
        "recent_commits": [{
            "sha": c["sha"][:7],
            "message": c["commit"]["message"][:100],
            "date": c["commit"]["author"]["date"],
        } for c in (commits[:5] if isinstance(commits, list) else [])],
        "files": [f["name"] for f in (tree if isinstance(tree, list) else [])],
    }
    return json.dumps(summary, ensure_ascii=False, default=str)


async def _gh_get_file(params: dict) -> str:
    owner = config.GITHUB_OWNER
    repo = params["repo"]
    path = params["path"]
    branch = params.get("branch", "main")

    result = await _github_request("GET", f"/repos/{owner}/{repo}/contents/{path}", params={"ref": branch})
    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)

    if isinstance(result, dict) and result.get("content"):
        file_size = result.get("size", 0)
        if file_size > 1_000_000:  # 1MB limit
            return json.dumps({
                "path": path,
                "size": file_size,
                "error": f"File too large ({file_size:,} bytes). Max 1MB.",
            }, ensure_ascii=False)
        import base64
        content = base64.b64decode(result["content"]).decode("utf-8", errors="replace")
        if len(content) > 8000:
            content = content[:8000] + "\n\n... [TRUNCATED — file too long]"
        return json.dumps({
            "path": path,
            "size": file_size,
            "content": content,
        }, ensure_ascii=False)

    return json.dumps(result, ensure_ascii=False, default=str)


async def _gh_list_commits(params: dict) -> str:
    owner = config.GITHUB_OWNER
    repo = params["repo"]
    limit = params.get("limit", 10)

    result = await _github_request("GET", f"/repos/{owner}/{repo}/commits", params={"per_page": limit})
    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)

    summary = [{
        "sha": c["sha"][:7],
        "message": c["commit"]["message"][:150],
        "author": c["commit"]["author"]["name"],
        "date": c["commit"]["author"]["date"],
    } for c in (result[:limit] if isinstance(result, list) else [])]
    return json.dumps(summary, ensure_ascii=False, default=str)


# ──── Railway implementations ────

async def _rw_list_projects(params: dict) -> str:
    query = """
    query {
        projects {
            edges {
                node {
                    id
                    name
                    updatedAt
                    services {
                        edges {
                            node {
                                id
                                name
                            }
                        }
                    }
                    environments {
                        edges {
                            node {
                                id
                                name
                            }
                        }
                    }
                }
            }
        }
    }
    """
    result = await _railway_gql(query)
    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)

    projects = []
    for edge in result.get("projects", {}).get("edges", []):
        node = edge["node"]
        services = [s["node"]["name"] for s in node.get("services", {}).get("edges", [])]
        projects.append({
            "id": node["id"],
            "name": node["name"],
            "updatedAt": node.get("updatedAt"),
            "services": services,
        })
    return json.dumps(projects, ensure_ascii=False, default=str)


async def _rw_get_deployments(params: dict) -> str:
    project_id = params["project_id"]
    query = """
    query($projectId: String!) {
        deployments(input: { projectId: $projectId }, first: 5) {
            edges {
                node {
                    id
                    status
                    createdAt
                    staticUrl
                    meta
                    service {
                        name
                    }
                }
            }
        }
    }
    """
    result = await _railway_gql(query, {"projectId": project_id})
    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)

    deployments = []
    for edge in result.get("deployments", {}).get("edges", []):
        d = edge["node"]
        deployments.append({
            "id": d["id"],
            "status": d["status"],
            "createdAt": d.get("createdAt"),
            "service": d.get("service", {}).get("name", ""),
            "url": d.get("staticUrl"),
        })
    return json.dumps(deployments, ensure_ascii=False, default=str)


async def _rw_get_variables(params: dict) -> str:
    project_id = params["project_id"]
    service_id = params.get("service_id", "")

    query = """
    query($projectId: String!, $serviceId: String) {
        variables(projectId: $projectId, serviceId: $serviceId, environmentId: null)
    }
    """
    result = await _railway_gql(query, {"projectId": project_id, "serviceId": service_id or None})
    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)

    # Mask sensitive values
    variables = result.get("variables", {})
    masked = {}
    for key, val in variables.items() if isinstance(variables, dict) else []:
        if any(s in key.upper() for s in ["KEY", "TOKEN", "SECRET", "PASSWORD", "SESSION"]):
            masked[key] = val[:8] + "..." if len(str(val)) > 8 else "***"
        else:
            masked[key] = val
    return json.dumps(masked, ensure_ascii=False, default=str)


async def _rw_redeploy(params: dict) -> str:
    deployment_id = params["deployment_id"]
    query = """
    mutation($id: String!) {
        deploymentRedeploy(id: $id) {
            id
            status
        }
    }
    """
    result = await _railway_gql(query, {"id": deployment_id})
    return json.dumps(result, ensure_ascii=False, default=str)


async def _rw_get_logs(params: dict) -> str:
    deployment_id = params["deployment_id"]
    limit = params.get("limit", 50)

    query = """
    query($deploymentId: String!, $limit: Int) {
        deploymentLogs(deploymentId: $deploymentId, limit: $limit) {
            message
            timestamp
            severity
        }
    }
    """
    result = await _railway_gql(query, {"deploymentId": deployment_id, "limit": limit})
    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)

    logs = result.get("deploymentLogs", [])
    if isinstance(logs, list):
        formatted = [f"[{l.get('severity', 'INFO')}] {l.get('message', '')}" for l in logs[-limit:]]
        return "\n".join(formatted) if formatted else "No logs found"
    return json.dumps(result, ensure_ascii=False, default=str)


# ──── Vercel implementations ────

async def _vc_list_projects(params: dict) -> str:
    result = await _vercel_request("GET", "/v9/projects")
    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)

    projects = []
    for p in result.get("projects", []):
        projects.append({
            "id": p.get("id"),
            "name": p.get("name"),
            "framework": p.get("framework"),
            "updatedAt": p.get("updatedAt"),
            "url": f"https://{p['name']}.vercel.app" if p.get("name") else None,
        })
    return json.dumps(projects, ensure_ascii=False, default=str)


async def _vc_get_deployments(params: dict) -> str:
    project_id = params["project_id"]
    limit = params.get("limit", 5)

    result = await _vercel_request("GET", f"/v6/deployments", params={
        "projectId": project_id,
        "limit": limit,
    })
    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)

    deployments = []
    for d in result.get("deployments", []):
        deployments.append({
            "id": d.get("uid"),
            "state": d.get("state"),
            "url": d.get("url"),
            "createdAt": d.get("createdAt"),
            "meta": {k: v for k, v in (d.get("meta", {}) or {}).items()
                     if k in ("githubCommitMessage", "githubCommitRef")},
        })
    return json.dumps(deployments, ensure_ascii=False, default=str)
