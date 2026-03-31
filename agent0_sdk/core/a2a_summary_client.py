"""
A2A client backed by an AgentSummary. Resolves the A2A interface from summary.a2a (agent card)
and exposes messageA2A, listTasks, loadTask with the same signatures as Agent.
Mirrors agent0-ts src/core/a2a-summary-client.ts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .models import AgentSummary
from .a2a import (
    MessageResponse,
    TaskResponse,
    TaskSummary,
    AgentTask,
    MessageA2AOptions,
    ListTasksOptions,
    LoadTaskOptions,
    A2APaymentRequired,
)
from .x402_types import X402RequiredResponse, X402Payment
from .x402_request import X402RequestDeps
from .a2a_client import (
    resolve_a2a_from_endpoint_url,
    send_message,
    list_tasks,
    get_task,
    create_task_handle,
    apply_credential,
)


def _is_x402_response(val: Any) -> bool:
    return getattr(val, "x402Required", False) or (isinstance(val, dict) and val.get("x402Required") is True)


class SDKLike:
    """Minimal SDK surface for A2A (avoids circular dependency)."""
    def getX402RequestDeps(self) -> Optional[X402RequestDeps]:
        raise NotImplementedError


class A2AClientFromSummary:
    """
    A2A client that wraps an AgentSummary. Resolves the agent card from summary.a2a on first use
    and delegates to the same low-level A2A functions as Agent.
    """

    def __init__(self, sdk: SDKLike, summary: AgentSummary) -> None:
        self._sdk = sdk
        self._summary = summary
        self._resolved: Optional[Dict[str, Any]] = None

    def _ensure_resolved(self) -> Dict[str, Any]:
        if self._resolved is not None:
            return self._resolved
        a2a = getattr(self._summary, "a2a", None) or getattr(self._summary, "A2A", None)
        if not a2a or not (str(a2a).startswith("http://") or str(a2a).startswith("https://")):
            raise RuntimeError("Agent summary has no A2A endpoint")
        self._resolved = resolve_a2a_from_endpoint_url(str(a2a))
        return self._resolved

    def messageA2A(
        self,
        content: Union[str, Dict[str, Any]],
        options: Optional[MessageA2AOptions] = None,
    ) -> Union[MessageResponse, TaskResponse, A2APaymentRequired]:
        resolved = self._ensure_resolved()
        x402_deps = self._sdk.getX402RequestDeps() if hasattr(self._sdk, "getX402RequestDeps") else None
        return send_message(
            resolved["baseUrl"],
            resolved["a2aVersion"],
            content,
            options=options,
            auth=resolved.get("auth"),
            tenant=resolved.get("tenant"),
            binding=resolved.get("binding"),
            x402_deps=x402_deps,
        )

    def listTasks(
        self,
        options: Optional[ListTasksOptions] = None,
    ) -> Union[List[TaskSummary], A2APaymentRequired]:
        resolved = self._ensure_resolved()
        x402_deps = self._sdk.getX402RequestDeps() if hasattr(self._sdk, "getX402RequestDeps") else None
        auth_dict: Optional[Dict[str, Any]] = None
        if resolved.get("auth"):
            auth_dict = apply_credential((options.credential or "") if options else "", resolved["auth"])
        else:
            auth_dict = {"headers": {}, "queryParams": {}}
        return list_tasks(
            resolved["baseUrl"],
            resolved["a2aVersion"],
            options=options,
            auth=auth_dict,
            tenant=resolved.get("tenant"),
            x402_deps=x402_deps,
        )

    def loadTask(
        self,
        task_id: str,
        options: Optional[LoadTaskOptions] = None,
    ) -> Union[AgentTask, A2APaymentRequired]:
        resolved = self._ensure_resolved()
        x402_deps = self._sdk.getX402RequestDeps() if hasattr(self._sdk, "getX402RequestDeps") else None
        resolved_auth: Optional[Dict[str, Any]] = None
        if resolved.get("auth"):
            resolved_auth = apply_credential((options.credential or "") if options else "", resolved["auth"])
        else:
            resolved_auth = {"headers": {}, "queryParams": {}}

        result = get_task(
            resolved["baseUrl"],
            resolved["a2aVersion"],
            task_id,
            auth=resolved_auth,
            x402_deps=x402_deps,
            payment=options.payment if options else None,
            tenant=resolved.get("tenant"),
        )

        if _is_x402_response(result):
            x402_resp = result
            x402_payment = getattr(x402_resp, "x402Payment", None) or x402_resp.get("x402Payment")
            if not x402_payment:
                raise RuntimeError("x402 response missing x402Payment")
            orig_pay = getattr(x402_payment, "pay", None) or x402_payment.get("pay")
            orig_pay_first = getattr(x402_payment, "pay_first", None) or x402_payment.get("pay_first")

            def pay_wrapper(accept: Any = None) -> AgentTask:
                summary_result = orig_pay(accept)
                tid = getattr(summary_result, "taskId", None) or (summary_result.get("taskId") if isinstance(summary_result, dict) else None)
                cid = getattr(summary_result, "contextId", None) or (summary_result.get("contextId") if isinstance(summary_result, dict) else "")
                if not tid:
                    raise RuntimeError("x402 pay() did not return taskId")
                return create_task_handle(
                    resolved["baseUrl"],
                    resolved["a2aVersion"],
                    str(tid),
                    str(cid or ""),
                    x402_deps,
                    resolved_auth,
                    resolved.get("tenant"),
                    None,
                )

            def pay_first_wrapper() -> AgentTask:
                if not orig_pay_first:
                    raise ValueError("x402: no pay_first available")
                summary_result = orig_pay_first()
                tid = getattr(summary_result, "taskId", None) or (summary_result.get("taskId") if isinstance(summary_result, dict) else None)
                cid = getattr(summary_result, "contextId", None) or (summary_result.get("contextId") if isinstance(summary_result, dict) else "")
                if not tid:
                    raise RuntimeError("x402 pay_first() did not return taskId")
                return create_task_handle(
                    resolved["baseUrl"],
                    resolved["a2aVersion"],
                    str(tid),
                    str(cid or ""),
                    x402_deps,
                    resolved_auth,
                    resolved.get("tenant"),
                    None,
                )

            wrapped_payment = X402Payment(
                accepts=getattr(x402_payment, "accepts", []) or x402_payment.get("accepts", []),
                pay=pay_wrapper,
                x402Version=getattr(x402_payment, "x402Version", None) or x402_payment.get("x402Version"),
                error=getattr(x402_payment, "error", None) or x402_payment.get("error"),
                resource=getattr(x402_payment, "resource", None) or x402_payment.get("resource"),
                price=getattr(x402_payment, "price", None) or x402_payment.get("price"),
                token=getattr(x402_payment, "token", None) or x402_payment.get("token"),
                network=getattr(x402_payment, "network", None) or x402_payment.get("network"),
                pay_first=pay_first_wrapper if orig_pay_first else None,
            )
            return A2APaymentRequired(x402Required=True, x402Payment=wrapped_payment)

        summary = result
        tid = getattr(summary, "taskId", None) or (summary.get("taskId") if isinstance(summary, dict) else task_id)
        cid = getattr(summary, "contextId", None) or (summary.get("contextId") if isinstance(summary, dict) else "")
        return create_task_handle(
            resolved["baseUrl"],
            resolved["a2aVersion"],
            str(tid),
            str(cid or ""),
            x402_deps,
            resolved_auth,
            resolved.get("tenant"),
            None,
        )


class A2AClientFromUrl:
    """
    A2A client backed directly by a URL (agent-card URL or base URL).
    Resolves the A2A interface once on first use.
    """

    def __init__(self, sdk: SDKLike, url: str) -> None:
        self._sdk = sdk
        self._url = url
        self._resolved: Optional[Dict[str, Any]] = None

    def _ensure_resolved(self) -> Dict[str, Any]:
        if self._resolved is not None:
            return self._resolved
        if not self._url or not (str(self._url).startswith("http://") or str(self._url).startswith("https://")):
            raise RuntimeError("A2A URL must be http or https")
        self._resolved = resolve_a2a_from_endpoint_url(str(self._url))
        return self._resolved

    def messageA2A(
        self,
        content: Union[str, Dict[str, Any]],
        options: Optional[MessageA2AOptions] = None,
    ) -> Union[MessageResponse, TaskResponse, A2APaymentRequired]:
        resolved = self._ensure_resolved()
        x402_deps = self._sdk.getX402RequestDeps() if hasattr(self._sdk, "getX402RequestDeps") else None
        return send_message(
            resolved["baseUrl"],
            resolved["a2aVersion"],
            content,
            options=options,
            auth=resolved.get("auth"),
            tenant=resolved.get("tenant"),
            binding=resolved.get("binding"),
            x402_deps=x402_deps,
        )

    def listTasks(
        self,
        options: Optional[ListTasksOptions] = None,
    ) -> Union[List[TaskSummary], A2APaymentRequired]:
        resolved = self._ensure_resolved()
        x402_deps = self._sdk.getX402RequestDeps() if hasattr(self._sdk, "getX402RequestDeps") else None
        auth_dict: Optional[Dict[str, Any]] = None
        if resolved.get("auth"):
            auth_dict = apply_credential((options.credential or "") if options else "", resolved["auth"])
        else:
            auth_dict = {"headers": {}, "queryParams": {}}
        return list_tasks(
            resolved["baseUrl"],
            resolved["a2aVersion"],
            options=options,
            auth=auth_dict,
            tenant=resolved.get("tenant"),
            x402_deps=x402_deps,
        )

    def loadTask(
        self,
        task_id: str,
        options: Optional[LoadTaskOptions] = None,
    ) -> Union[AgentTask, A2APaymentRequired]:
        resolved = self._ensure_resolved()
        x402_deps = self._sdk.getX402RequestDeps() if hasattr(self._sdk, "getX402RequestDeps") else None
        resolved_auth: Optional[Dict[str, Any]] = None
        if resolved.get("auth"):
            resolved_auth = apply_credential((options.credential or "") if options else "", resolved["auth"])
        else:
            resolved_auth = {"headers": {}, "queryParams": {}}

        result = get_task(
            resolved["baseUrl"],
            resolved["a2aVersion"],
            task_id,
            auth=resolved_auth,
            x402_deps=x402_deps,
            payment=options.payment if options else None,
            tenant=resolved.get("tenant"),
        )

        if _is_x402_response(result):
            x402_resp = result
            x402_payment = getattr(x402_resp, "x402Payment", None) or x402_resp.get("x402Payment")
            if not x402_payment:
                raise RuntimeError("x402 response missing x402Payment")
            orig_pay = getattr(x402_payment, "pay", None) or x402_payment.get("pay")
            orig_pay_first = getattr(x402_payment, "pay_first", None) or x402_payment.get("pay_first")

            def pay_wrapper(accept: Any = None) -> AgentTask:
                summary_result = orig_pay(accept)
                tid = getattr(summary_result, "taskId", None) or (summary_result.get("taskId") if isinstance(summary_result, dict) else None)
                cid = getattr(summary_result, "contextId", None) or (summary_result.get("contextId") if isinstance(summary_result, dict) else "")
                if not tid:
                    raise RuntimeError("x402 pay() did not return taskId")
                return create_task_handle(
                    resolved["baseUrl"],
                    resolved["a2aVersion"],
                    str(tid),
                    str(cid or ""),
                    x402_deps,
                    resolved_auth,
                    resolved.get("tenant"),
                    None,
                )

            def pay_first_wrapper() -> AgentTask:
                if not orig_pay_first:
                    raise ValueError("x402: no pay_first available")
                summary_result = orig_pay_first()
                tid = getattr(summary_result, "taskId", None) or (summary_result.get("taskId") if isinstance(summary_result, dict) else None)
                cid = getattr(summary_result, "contextId", None) or (summary_result.get("contextId") if isinstance(summary_result, dict) else "")
                if not tid:
                    raise RuntimeError("x402 pay_first() did not return taskId")
                return create_task_handle(
                    resolved["baseUrl"],
                    resolved["a2aVersion"],
                    str(tid),
                    str(cid or ""),
                    x402_deps,
                    resolved_auth,
                    resolved.get("tenant"),
                    None,
                )

            wrapped_payment = X402Payment(
                accepts=getattr(x402_payment, "accepts", []) or x402_payment.get("accepts", []),
                pay=pay_wrapper,
                x402Version=getattr(x402_payment, "x402Version", None) or x402_payment.get("x402Version"),
                error=getattr(x402_payment, "error", None) or x402_payment.get("error"),
                resource=getattr(x402_payment, "resource", None) or x402_payment.get("resource"),
                price=getattr(x402_payment, "price", None) or x402_payment.get("price"),
                token=getattr(x402_payment, "token", None) or x402_payment.get("token"),
                network=getattr(x402_payment, "network", None) or x402_payment.get("network"),
                pay_first=pay_first_wrapper if orig_pay_first else None,
            )
            return A2APaymentRequired(x402Required=True, x402Payment=wrapped_payment)

        summary = result
        tid = getattr(summary, "taskId", None) or (summary.get("taskId") if isinstance(summary, dict) else task_id)
        cid = getattr(summary, "contextId", None) or (summary.get("contextId") if isinstance(summary, dict) else "")
        return create_task_handle(
            resolved["baseUrl"],
            resolved["a2aVersion"],
            str(tid),
            str(cid or ""),
            x402_deps,
            resolved_auth,
            resolved.get("tenant"),
            None,
        )
