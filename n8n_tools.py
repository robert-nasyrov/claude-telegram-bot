"""
n8n integration via Claude Tool Use.
Claude decides when to call n8n API based on user's natural language requests.
"""

import asyncio
import logging
import json
from typing import Any

import httpx

import config

logger = logging.getLogger(__name__)


# ──────────────────── Tool Definitions ────────────────
# These are passed to Claude API so it knows what tools are available.

N8N_TOOLS = [
    {
        "name": "n8n_list_workflows",
        "description": (
            "List all workflows in n8n. Returns workflow names, IDs, active status, "
            "and last updated time. Use when user asks about their workflows, automations, "
            "or wants an overview of what's set up."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "active_only": {
                    "type": "boolean",
                    "description": "If true, return only active workflows. Default false.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
    {
        "name": "n8n_get_workflow",
        "description": (
            "Get detailed info about a specific workflow by ID. Returns all nodes, "
            "connections, settings. Use when user asks about a specific workflow's "
            "structure, what it does, or its configuration."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "The workflow ID to retrieve.",
                },
            },
            "required": ["workflow_id"],
        },
    },
    {
        "name": "n8n_activate_workflow",
        "description": (
            "Activate (enable) a workflow so it runs on its trigger/schedule. "
            "Use when user wants to turn on or start a workflow."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "The workflow ID to activate.",
                },
            },
            "required": ["workflow_id"],
        },
    },
    {
        "name": "n8n_deactivate_workflow",
        "description": (
            "Deactivate (disable) a workflow so it stops running. "
            "Use when user wants to turn off or pause a workflow."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "The workflow ID to deactivate.",
                },
            },
            "required": ["workflow_id"],
        },
    },
    {
        "name": "n8n_execute_workflow",
        "description": (
            "Manually trigger/execute a workflow right now. Optionally pass input data. "
            "Use when user wants to run a workflow immediately or test it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "The workflow ID to execute.",
                },
            },
            "required": ["workflow_id"],
        },
    },
    {
        "name": "n8n_get_executions",
        "description": (
            "Get recent executions (runs) of workflows. Can filter by workflow ID "
            "and status (success/error/waiting). Use when user asks about what ran, "
            "what failed, execution history, or errors."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "Filter by workflow ID. Optional — omit to see all.",
                    "default": "",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status: 'success', 'error', 'waiting', or empty for all.",
                    "enum": ["", "success", "error", "waiting"],
                    "default": "",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of executions to return. Default 10.",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
    {
        "name": "n8n_get_execution_detail",
        "description": (
            "Get detailed information about a specific execution, including all node "
            "outputs and errors. Use when user wants to debug a specific run."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "execution_id": {
                    "type": "string",
                    "description": "The execution ID to inspect.",
                },
            },
            "required": ["execution_id"],
        },
    },
    {
        "name": "n8n_update_workflow",
        "description": (
            "Update a workflow's nodes or settings. Takes the full workflow JSON. "
            "Use when user wants to modify a workflow — change a node's parameters, "
            "add or remove nodes, update credentials, etc. "
            "IMPORTANT: First get the current workflow with n8n_get_workflow, "
            "modify what's needed, then send the full updated JSON."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "The workflow ID to update.",
                },
                "workflow_data": {
                    "type": "object",
                    "description": (
                        "The full workflow object with modifications. "
                        "Must include 'nodes' and 'connections' at minimum."
                    ),
                },
            },
            "required": ["workflow_id", "workflow_data"],
        },
    },
]


# ──────────────────── API Client ──────────────────────

async def _n8n_request(
    method: str,
    path: str,
    json_data: dict = None,
    params: dict = None,
) -> dict | list | None:
    """Make authenticated request to n8n API."""
    base_url = config.N8N_API_URL.rstrip("/")
    url = f"{base_url}/api/v1{path}"

    headers = {
        "X-N8N-API-KEY": config.N8N_API_KEY,
        "Accept": "application/json",
    }

    last_error = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_data,
                    params=params,
                )

                if response.status_code >= 500:
                    last_error = f"n8n API {response.status_code}: {response.text[:300]}"
                    logger.warning(f"n8n API error (attempt {attempt+1}/3): {last_error}")
                    await asyncio.sleep(2 ** attempt)
                    continue

                if response.status_code >= 400:
                    logger.error(f"n8n API error: {response.status_code} {response.text[:500]}")
                    return {"error": f"n8n API returned {response.status_code}: {response.text[:300]}"}

                return response.json()
        except httpx.TimeoutException:
            last_error = f"n8n API timeout (attempt {attempt+1}/3)"
            logger.warning(last_error)
            await asyncio.sleep(2 ** attempt)
        except httpx.ConnectError as e:
            last_error = f"n8n API connection error: {e}"
            logger.warning(f"{last_error} (attempt {attempt+1}/3)")
            await asyncio.sleep(2 ** attempt)

    return {"error": last_error or "n8n API request failed after 3 attempts"}


# ──────────────────── Tool Executors ──────────────────

async def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute an n8n tool and return the result as a string for Claude."""
    try:
        if tool_name == "n8n_list_workflows":
            return await _list_workflows(tool_input)
        elif tool_name == "n8n_get_workflow":
            return await _get_workflow(tool_input)
        elif tool_name == "n8n_activate_workflow":
            return await _activate_workflow(tool_input)
        elif tool_name == "n8n_deactivate_workflow":
            return await _deactivate_workflow(tool_input)
        elif tool_name == "n8n_execute_workflow":
            return await _execute_workflow(tool_input)
        elif tool_name == "n8n_get_executions":
            return await _get_executions(tool_input)
        elif tool_name == "n8n_get_execution_detail":
            return await _get_execution_detail(tool_input)
        elif tool_name == "n8n_update_workflow":
            return await _update_workflow(tool_input)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
    except Exception as e:
        logger.error(f"Tool execution error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


async def _list_workflows(params: dict) -> str:
    active_only = params.get("active_only", False)
    result = await _n8n_request("GET", "/workflows")

    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)

    workflows = result.get("data", result) if isinstance(result, dict) else result

    if active_only and isinstance(workflows, list):
        workflows = [w for w in workflows if w.get("active")]

    # Summarize for Claude
    summary = []
    if isinstance(workflows, list):
        for w in workflows:
            summary.append({
                "id": w.get("id"),
                "name": w.get("name"),
                "active": w.get("active"),
                "updatedAt": w.get("updatedAt", ""),
                "tags": [t.get("name", "") for t in w.get("tags", [])],
            })

    return json.dumps(summary, ensure_ascii=False, default=str)


async def _get_workflow(params: dict) -> str:
    wf_id = params["workflow_id"]
    result = await _n8n_request("GET", f"/workflows/{wf_id}")

    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)

    # Extract key info — full JSON can be huge, summarize nodes
    if isinstance(result, dict):
        nodes_summary = []
        for node in result.get("nodes", []):
            nodes_summary.append({
                "name": node.get("name"),
                "type": node.get("type"),
                "parameters_keys": list(node.get("parameters", {}).keys()),
                "position": node.get("position"),
            })

        summary = {
            "id": result.get("id"),
            "name": result.get("name"),
            "active": result.get("active"),
            "nodes_count": len(result.get("nodes", [])),
            "nodes": nodes_summary,
            "connections_count": len(result.get("connections", {})),
            "updatedAt": result.get("updatedAt"),
            "settings": result.get("settings", {}),
        }
        return json.dumps(summary, ensure_ascii=False, default=str)

    return json.dumps(result, ensure_ascii=False, default=str)


async def _activate_workflow(params: dict) -> str:
    wf_id = params["workflow_id"]
    result = await _n8n_request("PATCH", f"/workflows/{wf_id}", json_data={"active": True})
    if isinstance(result, dict):
        return json.dumps({
            "success": True,
            "id": result.get("id"),
            "name": result.get("name"),
            "active": result.get("active"),
        }, ensure_ascii=False)
    return json.dumps(result, default=str)


async def _deactivate_workflow(params: dict) -> str:
    wf_id = params["workflow_id"]
    result = await _n8n_request("PATCH", f"/workflows/{wf_id}", json_data={"active": False})
    if isinstance(result, dict):
        return json.dumps({
            "success": True,
            "id": result.get("id"),
            "name": result.get("name"),
            "active": result.get("active"),
        }, ensure_ascii=False)
    return json.dumps(result, default=str)


async def _execute_workflow(params: dict) -> str:
    wf_id = params["workflow_id"]
    result = await _n8n_request("POST", f"/workflows/{wf_id}/run", json_data={})

    if isinstance(result, dict) and "error" in result:
        # Some n8n versions use different endpoint
        result = await _n8n_request("POST", f"/executions", json_data={"workflowId": wf_id})

    return json.dumps(result, ensure_ascii=False, default=str)


async def _get_executions(params: dict) -> str:
    query_params = {"limit": params.get("limit", 10)}

    wf_id = params.get("workflow_id", "")
    if wf_id:
        query_params["workflowId"] = wf_id

    status = params.get("status", "")
    if status:
        query_params["status"] = status

    result = await _n8n_request("GET", "/executions", params=query_params)

    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)

    executions = result.get("data", result) if isinstance(result, dict) else result

    summary = []
    if isinstance(executions, list):
        for ex in executions[:params.get("limit", 10)]:
            summary.append({
                "id": ex.get("id"),
                "workflowId": ex.get("workflowId"),
                "workflowName": ex.get("workflowData", {}).get("name", "")
                    if isinstance(ex.get("workflowData"), dict) else "",
                "status": ex.get("status"),
                "startedAt": ex.get("startedAt", ""),
                "stoppedAt": ex.get("stoppedAt", ""),
                "mode": ex.get("mode", ""),
            })

    return json.dumps(summary, ensure_ascii=False, default=str)


async def _get_execution_detail(params: dict) -> str:
    ex_id = params["execution_id"]
    # includeData=true is REQUIRED to get node-level execution details
    result = await _n8n_request("GET", f"/executions/{ex_id}", params={"includeData": "true"})

    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)

    if isinstance(result, dict):
        # n8n API can nest data differently depending on version
        # Try multiple paths to find runData
        run_data = None

        # Path 1: result.data.resultData.runData (n8n cloud)
        if isinstance(result.get("data"), dict):
            rd = result["data"].get("resultData", {})
            if isinstance(rd, dict):
                run_data = rd.get("runData")

        # Path 2: result.resultData.runData
        if not run_data and isinstance(result.get("resultData"), dict):
            run_data = result["resultData"].get("runData")

        # Path 3: result.data.data.resultData.runData (double nested)
        if not run_data and isinstance(result.get("data"), dict):
            inner = result["data"].get("data", {})
            if isinstance(inner, dict):
                rd = inner.get("resultData", {})
                if isinstance(rd, dict):
                    run_data = rd.get("runData")

        node_results = {}
        if isinstance(run_data, dict):
            for node_name, runs in run_data.items():
                if isinstance(runs, list) and runs:
                    last_run = runs[-1]
                    error_info = last_run.get("error")

                    # Extract input/output data for debugging
                    node_data = {}
                    main_data = last_run.get("data", {}).get("main", [])
                    if isinstance(main_data, list) and main_data:
                        first_set = main_data[0] if main_data else []
                        if isinstance(first_set, list):
                            node_data["items_count"] = len(first_set)
                            # Include first item's keys for context
                            if first_set:
                                first_item = first_set[0]
                                if isinstance(first_item, dict):
                                    json_data = first_item.get("json", first_item)
                                    if isinstance(json_data, dict):
                                        node_data["first_item_keys"] = list(json_data.keys())[:10]
                                        # Truncated preview of first item
                                        preview = json.dumps(json_data, ensure_ascii=False, default=str)
                                        node_data["first_item_preview"] = preview[:500]

                    node_results[node_name] = {
                        "status": "error" if error_info else "success",
                        "error": None,
                        "data": node_data,
                        "executionTime": last_run.get("executionTime"),
                    }

                    if error_info:
                        if isinstance(error_info, dict):
                            node_results[node_name]["error"] = {
                                "message": str(error_info.get("message", ""))[:500],
                                "description": str(error_info.get("description", ""))[:500],
                                "stack": str(error_info.get("stack", ""))[:300],
                            }
                        else:
                            node_results[node_name]["error"] = str(error_info)[:500]

        # Also extract the error node if flagged at top level
        top_error = None
        if isinstance(result.get("data"), dict):
            re = result["data"].get("resultData", {})
            if isinstance(re, dict) and re.get("error"):
                top_error = str(re["error"])[:500]

        summary = {
            "id": result.get("id"),
            "status": result.get("status") or result.get("finished"),
            "startedAt": result.get("startedAt"),
            "stoppedAt": result.get("stoppedAt"),
            "workflowName": result.get("workflowData", {}).get("name", "") if isinstance(result.get("workflowData"), dict) else "",
            "node_results": node_results,
            "nodes_count": len(node_results),
            "error_nodes": [k for k, v in node_results.items() if v.get("status") == "error"],
            "top_level_error": top_error,
        }
        return json.dumps(summary, ensure_ascii=False, default=str)

    return json.dumps(result, ensure_ascii=False, default=str)


async def _update_workflow(params: dict) -> str:
    wf_id = params["workflow_id"]
    wf_data = params["workflow_data"]
    result = await _n8n_request("PATCH", f"/workflows/{wf_id}", json_data=wf_data)

    if isinstance(result, dict):
        return json.dumps({
            "success": not result.get("error"),
            "id": result.get("id"),
            "name": result.get("name"),
            "active": result.get("active"),
            "updatedAt": result.get("updatedAt"),
        }, ensure_ascii=False, default=str)
    return json.dumps(result, default=str)
