"""
A2A (Agent-to-Agent) HTTP client: message:send, task query/cancel, response parsing.
Mirrors agent0-ts src/core/a2a-client.ts. Sync with requests.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Union
from urllib.parse import urlencode, quote

import requests

from .a2a import (
    Part,
    MessageResponse,
    TaskResponse,
    TaskSummary,
    TaskState,
    AgentTask,
    AgentCardAuth,
    MessageA2AOptions,
    ListTasksOptions,
    LoadTaskOptions,
)
from .x402_types import X402RequiredResponse, is_x402_required
from .x402_request import request_with_x402, X402RequestDeps

ERR_402 = "A2A server returned 402 Payment Required"
ERR_NEITHER = "A2A response contained neither task nor message"

Binding = str  # "HTTP+JSON" | "JSONRPC" | "GRPC" | "AUTO"


def normalize_binding(raw: Any) -> Binding:
    s = str(raw).strip().upper().replace("-", "") if raw else ""
    if s in ("HTTP+JSON", "JSONRPC", "GRPC"):
        return s
    return "AUTO"


def normalize_interfaces(card: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    if not card or not isinstance(card, dict):
        return result
    if isinstance(card.get("supportedInterfaces"), list) and card["supportedInterfaces"]:
        for i in card["supportedInterfaces"]:
            if not isinstance(i, dict):
                continue
            url = (i.get("url") or "").strip()
            if not url or not (url.startswith("http://") or url.startswith("https://")):
                continue
            result.append({
                "url": url.rstrip("/"),
                "binding": normalize_binding(i.get("protocolBinding") or i.get("protocol")),
                "version": i.get("protocolVersion") if isinstance(i.get("protocolVersion"), str) else None,
                "tenant": i.get("tenant") if isinstance(i.get("tenant"), str) else None,
            })
        return result
    primary = normalize_binding(card.get("preferredTransport"))
    if isinstance(card.get("url"), str) and (card["url"].startswith("http://") or card["url"].startswith("https://")):
        result.append({
            "url": card["url"].strip().rstrip("/"),
            "binding": primary,
            "version": card.get("protocolVersion") if isinstance(card.get("protocolVersion"), str) else None,
            "tenant": None,
        })
    for i in (card.get("additionalInterfaces") or []):
        if not isinstance(i, dict):
            continue
        url = (i.get("url") or "").strip()
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            continue
        result.append({
            "url": url.rstrip("/"),
            "binding": normalize_binding(i.get("transport") or i.get("protocolBinding")),
            "version": i.get("protocolVersion") if isinstance(i.get("protocolVersion"), str) else None,
            "tenant": i.get("tenant") if isinstance(i.get("tenant"), str) else None,
        })
    return result


PREFERRED_BINDINGS: List[Binding] = ["HTTP+JSON", "JSONRPC", "GRPC", "AUTO"]


def pick_interface(
    interfaces: List[Dict[str, Any]],
    preferred_bindings: Optional[List[Binding]] = None,
) -> Optional[Dict[str, Any]]:
    base = preferred_bindings or PREFERRED_BINDINGS
    allowed = set(base + ["AUTO"])
    supported = [i for i in interfaces if i.get("binding") in allowed]
    if not supported:
        return None
    def index_of(b: str) -> int:
        try:
            return base.index(b)
        except ValueError:
            return len(base)
    supported.sort(
        key=lambda x: (
            -(len(str(x.get("version") or ""))),
            index_of(x.get("binding") or "AUTO"),
            1 if (x.get("binding") == "AUTO") else 0,
        )
    )
    return supported[0]


def resolve_a2a_from_endpoint_url(url: str, timeout: int = 5) -> Dict[str, Any]:
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("A2A endpoint URL must be http or https")
    data: Optional[Dict[str, Any]] = None
    if re.search(r"/(\.well-known/)?(agent-card|agent)\.json$", url, re.I):
        r = requests.get(url, timeout=timeout, allow_redirects=True)
        if not r.ok:
            raise RuntimeError(f"Failed to fetch agent card: HTTP {r.status_code}")
        data = r.json()
    else:
        base = url.rstrip("/")
        for path in ["/.well-known/agent-card.json", "/.well-known/agent.json"]:
            try:
                r = requests.get(base + path, timeout=timeout, allow_redirects=True)
                if r.ok:
                    data = r.json()
                    break
                if r.status_code != 404:
                    raise RuntimeError(f"Failed to fetch agent card: HTTP {r.status_code}")
            except requests.RequestException as e:
                raise RuntimeError(f"Failed to fetch agent card: {e}") from e
    if not data:
        raise RuntimeError("Could not load agent card from A2A endpoint")
    default_version = "0.3"
    interfaces = normalize_interfaces(data)
    chosen = pick_interface(interfaces, ["HTTP+JSON", "JSONRPC"])
    base_url = ""
    a2a_version = default_version
    binding: Binding = "AUTO"
    tenant: Optional[str] = None
    if chosen:
        base_url = chosen["url"]
        a2a_version = chosen.get("version") or default_version
        binding = chosen.get("binding") or "AUTO"
        tenant = chosen.get("tenant")
    else:
        for src in [data.get("supportedInterfaces"), data.get("additionalInterfaces"), [{"url": data.get("url")}]]:
            if isinstance(src, list) and src and isinstance(src[0], dict):
                u = src[0].get("url")
                if isinstance(u, str) and (u.startswith("http://") or u.startswith("https://")):
                    base_url = u.rstrip("/")
                    break
        if not base_url and isinstance(data.get("url"), str):
            base_url = data["url"].rstrip("/")
        if not base_url:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            path = parsed.path or "/"
            path = re.sub(r"/(\.well-known/)?(agent-card|agent)\.json$", "", path, flags=re.I) or "/"
            base_url = f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")
        for src in [data.get("supportedInterfaces"), data.get("additionalInterfaces")]:
            if isinstance(src, list) and src and isinstance(src[0], dict):
                v = src[0].get("protocolVersion")
                if isinstance(v, str):
                    a2a_version = v
                    break
        if a2a_version == default_version:
            a2a_version = (
                data.get("protocolVersion")
                or data.get("version")
                or default_version
            )
    auth: Optional[AgentCardAuth] = None
    if data.get("securitySchemes") or data.get("security"):
        auth = AgentCardAuth(
            securitySchemes=data.get("securitySchemes"),
            security=data.get("security"),
        )
    return {
        "baseUrl": base_url,
        "a2aVersion": a2a_version,
        "binding": binding,
        "tenant": tenant,
        "auth": auth,
    }


def normalize_credential(credential: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    return {"apiKey": credential} if isinstance(credential, str) else credential


def apply_credential(credential: Union[str, Dict[str, Any]], auth: AgentCardAuth) -> Dict[str, Any]:
    headers: Dict[str, str] = {}
    query_params: Dict[str, str] = {}
    obj = normalize_credential(credential)
    schemes = auth.securitySchemes or {}
    security = auth.security or []
    for entry in security:
        if not entry or not isinstance(entry, dict):
            continue
        name = next(iter(entry.keys()), None)
        if not name:
            continue
        scheme = schemes.get(name)
        if not scheme or not isinstance(scheme, dict):
            continue
        value = obj.get(name)
        if value is None or not isinstance(value, str) or value == "":
            continue
        if scheme.get("type") == "apiKey":
            where = scheme.get("in", "header")
            n = scheme.get("name", name)
            if where == "header":
                headers[n] = value
            elif where == "query":
                query_params[n] = value
            elif where == "cookie":
                headers["Cookie"] = f"{n}={quote(value)}"
        elif scheme.get("type") == "http":
            if scheme.get("scheme") == "bearer":
                headers["Authorization"] = f"Bearer {value}"
            elif scheme.get("scheme") == "basic":
                import base64
                encoded = base64.b64encode(value.encode("utf-8")).decode("ascii") if ":" in value or not value.replace("+", "").replace("/", "").replace("=", "").isalnum() else value
                headers["Authorization"] = f"Basic {encoded}"
        return {"headers": headers, "queryParams": query_params}
    return {"headers": headers, "queryParams": query_params}


def _part_from_dict(p: Any) -> Part:
    """Build Part from dict (v0.3 kind/text/file/data or flat text/url/data/raw)."""
    if isinstance(p, Part):
        return p
    if not isinstance(p, dict):
        return Part(text="")
    kind = p.get("kind")
    if kind == "text":
        return Part(text=p.get("text") or "")
    if kind == "file" and isinstance(p.get("file"), dict):
        f = p["file"]
        return Part(url=f.get("uri"), raw=f.get("bytes"))
    if kind == "data":
        return Part(data=p.get("data"))
    return Part(
        text=p.get("text"),
        url=p.get("url"),
        data=p.get("data"),
        raw=p.get("raw"),
        extra={k: v for k, v in p.items() if k not in ("text", "url", "data", "raw")},
    )


def parts_for_send(parts: List[Part], a2a_version: str) -> List[Dict[str, Any]]:
    v = (a2a_version or "").strip()
    if not v.startswith("0."):
        return [{"text": p.text, "url": p.url, "data": p.data, "raw": p.raw, **p.extra} for p in parts]
    out = []
    for p in parts:
        if p.text is not None:
            out.append({"kind": "text", "text": p.text})
        elif p.url is not None:
            out.append({"kind": "file", "file": {"uri": p.url}})
        elif p.data is not None:
            out.append({"kind": "data", "data": p.data})
        elif p.raw is not None:
            out.append({"kind": "file", "file": {"bytes": p.raw}})
        else:
            out.append({"kind": "text", "text": ""})
    return out


def a2a_headers(a2a_version: str, auth: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    base = {"Content-Type": "application/json", "A2A-Version": a2a_version}
    if auth and auth.get("headers"):
        base.update(auth["headers"])
    return base


def append_query_params(url: str, query_params: Dict[str, str]) -> str:
    if not query_params:
        return url
    sep = "&" if "?" in url else "?"
    return url + sep + urlencode(query_params)


def get_message_send_paths_to_try(a2a_version: str, tenant: Optional[str] = None) -> List[str]:
    v = (a2a_version or "").strip()
    prefix = f"/tenants/{quote(tenant)}" if tenant else ""
    first = "/v1/message:send" if v.startswith("0.") else "/message:send"
    second = "/message:send" if v.startswith("0.") else "/v1/message:send"
    return [prefix + first, prefix + second]


def build_path_suffix(
    operation: str,
    a2a_version: str,
    tenant: Optional[str] = None,
    task_id: Optional[str] = None,
) -> str:
    v = (a2a_version or "").strip()
    use_v1 = v.startswith("0.")
    prefix = f"/tenants/{quote(tenant)}" if tenant else ""
    if operation == "message:send":
        return prefix + ("/v1/message:send" if use_v1 else "/message:send")
    if operation == "tasks":
        return prefix + ("/v1/tasks" if use_v1 else "/tasks")
    if operation == "task" and task_id:
        return prefix + ("/v1/tasks/" if use_v1 else "/tasks/") + quote(task_id)
    if operation == "taskCancel" and task_id:
        return prefix + ("/v1/tasks/" if use_v1 else "/tasks/") + quote(task_id) + ":cancel"
    return prefix + "/message:send"


def parse_message_send_response(
    data: Dict[str, Any],
    create_task_handle: Callable[..., AgentTask],
    base_url: str,
    a2a_version: str,
    x402_deps: Optional[X402RequestDeps] = None,
    auth: Optional[Dict[str, Any]] = None,
) -> Union[MessageResponse, TaskResponse]:
    """create_task_handle is called with (base_url, a2a_version, task_id, context_id) only."""
    if data.get("task") is not None and isinstance(data["task"], dict):
        t = data["task"]
        task_id = str(t.get("id") or t.get("taskId") or "")
        context_id = str(t.get("contextId") or "")
        if not task_id:
            raise ValueError("A2A task response missing task id")
        task = create_task_handle(base_url, a2a_version, task_id, context_id)
        return TaskResponse(
            taskId=task_id,
            contextId=context_id,
            task=task,
            status=TaskState(state=t.get("state"), extra={k: v for k, v in t.items() if k not in ("id", "taskId", "contextId", "status", "state")}),
        )
    if data.get("message") is not None and isinstance(data["message"], dict):
        msg = data["message"]
        parts = msg.get("parts")
        return MessageResponse(
            content=msg.get("content") if isinstance(msg.get("content"), str) else None,
            parts=parts if isinstance(parts, list) else None,
            contextId=msg.get("contextId") if isinstance(msg.get("contextId"), str) else None,
        )
    raise RuntimeError(ERR_NEITHER)


def create_task_handle(
    base_url: str,
    a2a_version: str,
    task_id: str,
    context_id: str,
    x402_deps: Optional[X402RequestDeps] = None,
    auth: Optional[Dict[str, Any]] = None,
    tenant: Optional[str] = None,
    fetch_fn: Optional[Callable[..., Any]] = None,
) -> AgentTask:
    base = base_url.rstrip("/")
    if fetch_fn is None:
        def _fetch(url: str, method: str, headers: Dict[str, str], body: Any, **kwargs: Any) -> Any:
            payload = kwargs.get("payment_payload")
            h = dict(headers)
            if payload and kwargs.get("payment_header_name"):
                h[kwargs["payment_header_name"]] = payload
            return requests.request(method, url, headers=h, data=body)
        fetch_fn = _fetch

    class TaskHandle(AgentTask):
        def query(self, options: Optional[Dict[str, Any]] = None) -> Any:
            q = f"?historyLength={options.get('historyLength')}" if options and options.get("historyLength") is not None else ""
            path = build_path_suffix("task", a2a_version, tenant, task_id) + q
            url = append_query_params(base + path, (auth or {}).get("queryParams", {}))
            if x402_deps:
                result = request_with_x402(
                    {"url": url, "method": "GET", "headers": a2a_headers(a2a_version, auth)},
                    x402_deps,
                )
                return result
            r = requests.get(url, headers=a2a_headers(a2a_version, auth))
            if r.status_code == 402:
                raise RuntimeError(ERR_402)
            r.raise_for_status()
            data = r.json()
            return {
                "taskId": str(data.get("id") or data.get("taskId") or task_id),
                "contextId": str(data.get("contextId") or context_id),
                "status": data.get("status"),
                "artifacts": data.get("artifacts"),
                "messages": data.get("history") or data.get("messages"),
            }

        def message(self, content: Union[str, Dict[str, Any]]) -> Any:
            parts: List[Part] = []
            if isinstance(content, str):
                parts = [Part(text=content)]
            elif isinstance(content, dict) and isinstance(content.get("parts"), list):
                parts = [_part_from_dict(p) for p in content["parts"]]
            msg = {
                "role": "ROLE_USER",
                "parts": parts_for_send(parts, a2a_version),
                "taskId": task_id,
                "contextId": context_id,
                "messageId": f"msg-{hash(id(self)) % 10**11}",
            }
            body = json.dumps({"message": msg})
            paths = get_message_send_paths_to_try(a2a_version, tenant)
            url = append_query_params(base + paths[0], (auth or {}).get("queryParams", {}))
            if x402_deps:
                return request_with_x402(
                    {"url": url, "method": "POST", "headers": a2a_headers(a2a_version, auth), "body": body},
                    x402_deps,
                )
            r = requests.post(url, headers=a2a_headers(a2a_version, auth), data=body)
            if r.status_code == 402:
                raise RuntimeError(ERR_402)
            r.raise_for_status()
            data = r.json()
            return parse_message_send_response(
                data,
                lambda b, v, tid, cid: create_task_handle(b, v, tid, cid, x402_deps, auth, tenant, fetch_fn),
                base_url,
                a2a_version,
                x402_deps,
                auth,
            )

        def cancel(self) -> Any:
            path = build_path_suffix("taskCancel", a2a_version, tenant, task_id)
            url = append_query_params(base + path, (auth or {}).get("queryParams", {}))
            if x402_deps:
                return request_with_x402(
                    {"url": url, "method": "POST", "headers": a2a_headers(a2a_version, auth), "body": "{}"},
                    x402_deps,
                )
            r = requests.post(url, headers=a2a_headers(a2a_version, auth), data="{}")
            if r.status_code == 402:
                raise RuntimeError(ERR_402)
            r.raise_for_status()
            data = r.json()
            return {"taskId": str(data.get("id") or task_id), "contextId": str(data.get("contextId") or context_id), "status": data.get("status")}

    def create_task(b: str, v: str, tid: str, cid: str) -> AgentTask:
        return create_task_handle(b, v, tid, cid, x402_deps, auth, tenant, fetch_fn)

    th = TaskHandle(task_id, context_id)
    # Bind methods so parse_message_send_response's 4-arg callback can create new handles
    def _query(options: Optional[Dict[str, Any]] = None) -> Any:
        return TaskHandle.query(th, options)
    def _message(content: Union[str, Dict[str, Any]]) -> Any:
        return TaskHandle.message(th, content)
    def _cancel() -> Any:
        return TaskHandle.cancel(th)
    th.query = _query  # type: ignore
    th.message = _message  # type: ignore
    th.cancel = _cancel  # type: ignore
    return th


def get_task(
    base_url: str,
    a2a_version: str,
    task_id: str,
    auth: Optional[Dict[str, Any]] = None,
    x402_deps: Optional[X402RequestDeps] = None,
    payment: Optional[str] = None,
    tenant: Optional[str] = None,
) -> Any:
    path = build_path_suffix("task", a2a_version, tenant, task_id)
    url = append_query_params(base_url.rstrip("/") + path, (auth or {}).get("queryParams", {}))
    if x402_deps:
        opts = {"url": url, "method": "GET", "headers": a2a_headers(a2a_version, auth), "payment": payment}
        opts["parseResponse"] = lambda res: _to_task_summary(
            res.json() if hasattr(res, "json") else json.loads(res.text), task_id
        )
        return request_with_x402(opts, x402_deps)
    r = requests.get(url, headers=a2a_headers(a2a_version, auth))
    if r.status_code == 402:
        raise RuntimeError(ERR_402)
    r.raise_for_status()
    data = r.json()
    return _to_task_summary(data, task_id)


def _to_task_summary(data: Dict[str, Any], task_id: str) -> TaskSummary:
    tid = str(data.get("id") or data.get("taskId") or task_id)
    cid = str(data.get("contextId") or "")
    st = data.get("status")
    if isinstance(st, dict):
        status = TaskState(state=st.get("state"), extra=st)
    elif isinstance(st, str):
        status = TaskState(state=st, extra={})
    else:
        status = None
    return TaskSummary(
        taskId=tid,
        contextId=cid,
        status=status,
        messages=data.get("history") or data.get("messages"),
        extra={k: v for k, v in data.items() if k not in ("id", "taskId", "contextId", "status", "history", "messages")},
    )


def list_tasks(
    base_url: str,
    a2a_version: str,
    options: Optional[ListTasksOptions] = None,
    auth: Optional[Dict[str, Any]] = None,
    tenant: Optional[str] = None,
    x402_deps: Optional[X402RequestDeps] = None,
) -> Any:
    path = build_path_suffix("tasks", a2a_version, tenant)
    q: Dict[str, str] = {"pageSize": "100"}
    if options and options.filter:
        if options.filter.get("contextId"):
            q["contextId"] = options.filter["contextId"]
        if options.filter.get("status"):
            q["status"] = options.filter["status"]
    if options and options.historyLength is not None:
        q["historyLength"] = str(options.historyLength)
    url = base_url.rstrip("/") + path + "?" + urlencode(q)
    url = append_query_params(url, (auth or {}).get("queryParams", {}))
    if x402_deps:
        def parse_list(res: Any) -> List[TaskSummary]:
            data = res.json() if hasattr(res, "json") else json.loads(res.text)
            tasks = data.get("tasks") or data.get("items") or data.get("results") or []
            return [_to_task_summary(t, t.get("taskId") or t.get("id") or "") for t in tasks]
        return request_with_x402(
            {"url": url, "method": "GET", "headers": a2a_headers(a2a_version, auth), "payment": options.payment if options else None, "parseResponse": parse_list},
            x402_deps,
        )
    r = requests.get(url, headers=a2a_headers(a2a_version, auth))
    if r.status_code == 402:
        raise RuntimeError(ERR_402)
    r.raise_for_status()
    data = r.json()
    tasks = data.get("tasks") or data.get("items") or data.get("results") or []
    return [_to_task_summary(t, str(t.get("taskId") or t.get("id") or "")) for t in tasks]


def send_message(
    base_url: str,
    a2a_version: str,
    content: Union[str, Dict[str, Any]],
    options: Optional[MessageA2AOptions] = None,
    auth: Optional[AgentCardAuth] = None,
    tenant: Optional[str] = None,
    binding: Optional[str] = None,
    x402_deps: Optional[X402RequestDeps] = None,
) -> Any:
    opts = options or MessageA2AOptions()
    if auth:
        resolved_auth = apply_credential(opts.credential or "", auth)
    else:
        resolved_auth = {"headers": {}, "queryParams": {}}
    parts: List[Part] = []
    if isinstance(content, str):
        parts = [Part(text=content)]
    elif isinstance(content, dict) and isinstance(content.get("parts"), list):
        parts = [_part_from_dict(p) for p in content["parts"]]
    message = {
        "role": "ROLE_USER",
        "parts": parts_for_send(parts, a2a_version),
        "messageId": f"msg-{id(opts) % 10**11}",
    }
    if opts.contextId:
        message["contextId"] = opts.contextId
    if opts.taskId:
        message["taskId"] = opts.taskId
    body = {"message": message}
    if opts.blocking is not None or opts.historyLength is not None or opts.acceptedOutputModes or opts.pushNotificationConfig is not None or opts.returnImmediately is not None:
        body["configuration"] = {}
        if opts.blocking is not None:
            body["configuration"]["blocking"] = opts.blocking
        if opts.historyLength is not None:
            body["configuration"]["historyLength"] = opts.historyLength
        if opts.acceptedOutputModes:
            body["configuration"]["acceptedOutputModes"] = opts.acceptedOutputModes
        if opts.pushNotificationConfig is not None:
            body["configuration"]["pushNotificationConfig"] = opts.pushNotificationConfig
        if opts.returnImmediately is not None:
            body["configuration"]["returnImmediately"] = opts.returnImmediately
    paths = get_message_send_paths_to_try(a2a_version, tenant)
    body_str = json.dumps(body)
    if x402_deps:
        def parse_res(res: Any) -> Union[MessageResponse, TaskResponse]:
            data = res.json() if hasattr(res, "json") else json.loads(res.text)
            return parse_message_send_response(
                data,
                lambda b, v, tid, cid: create_task_handle(b, v, tid, cid, x402_deps, resolved_auth, tenant, None),
                base_url,
                a2a_version,
                x402_deps,
                resolved_auth,
            )
        last_err: Optional[Exception] = None
        for path in paths:
            url = append_query_params(base_url.rstrip("/") + path, resolved_auth.get("queryParams", {}))
            try:
                return request_with_x402(
                    {"url": url, "method": "POST", "headers": a2a_headers(a2a_version, resolved_auth), "body": body_str, "payment": opts.payment, "parseResponse": parse_res},
                    x402_deps,
                )
            except RuntimeError as e:
                last_err = e
                if "404" in str(e):
                    continue
                raise
        raise (last_err or RuntimeError("A2A request failed"))
    for path in paths:
        u = append_query_params(base_url.rstrip("/") + path, resolved_auth.get("queryParams", {}))
        r = requests.post(u, headers=a2a_headers(a2a_version, resolved_auth), data=body_str)
        if r.status_code == 402:
            raise RuntimeError(ERR_402)
        if r.ok:
            data = r.json()
            return parse_message_send_response(
                data,
                lambda b, v, tid, cid: create_task_handle(b, v, tid, cid, None, resolved_auth, tenant, None),
                base_url,
                a2a_version,
                None,
                resolved_auth,
            )
        if r.status_code != 404:
            break
    raise RuntimeError(f"A2A request failed: HTTP {r.status_code}")
