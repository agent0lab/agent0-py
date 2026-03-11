"""
A2A (Agent-to-Agent) types.
Mirrors agent0-ts src/models/a2a.ts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


CredentialObject = Dict[str, Any]


@dataclass
class MessageA2AOptions:
    blocking: Optional[bool] = None
    contextId: Optional[str] = None
    taskId: Optional[str] = None
    credential: Optional[Union[str, CredentialObject]] = None
    payment: Optional[str] = None
    acceptedOutputModes: Optional[List[str]] = None
    historyLength: Optional[int] = None
    pushNotificationConfig: Optional[Dict[str, Any]] = None
    returnImmediately: Optional[bool] = None


SecurityScheme = Dict[str, Any]


@dataclass
class AgentCardAuth:
    securitySchemes: Optional[Dict[str, SecurityScheme]] = None
    security: Optional[List[Dict[str, List[str]]]] = None


@dataclass
class Part:
    text: Optional[str] = None
    url: Optional[str] = None
    data: Optional[str] = None
    raw: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MessageResponse:
    x402Required: bool = False
    content: Optional[str] = None
    parts: Optional[List[Part]] = None
    contextId: Optional[str] = None


@dataclass
class TaskState:
    state: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class A2APaymentRequired:
    x402Required: bool = True
    x402Payment: Any = None


@dataclass
class TaskSummary:
    x402Required: bool = False
    taskId: str = ""
    contextId: str = ""
    status: Optional[TaskState] = None
    messages: Optional[List[Any]] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ListTasksOptions:
    filter: Optional[Dict[str, Any]] = None
    historyLength: Optional[int] = None
    credential: Optional[Union[str, CredentialObject]] = None
    payment: Optional[str] = None


@dataclass
class LoadTaskOptions:
    credential: Optional[Union[str, CredentialObject]] = None
    payment: Optional[str] = None


class AgentTask:
    """Task handle: taskId, contextId, query(), message(), cancel()."""
    def __init__(self, taskId: str, contextId: str):
        self.taskId = taskId
        self.contextId = contextId

    def query(self, options: Optional[Dict[str, Any]] = None) -> Any:
        raise NotImplementedError

    def message(self, content: Union[str, Dict[str, Any]]) -> Any:
        raise NotImplementedError

    def cancel(self) -> Any:
        raise NotImplementedError


@dataclass
class TaskResponse:
    x402Required: bool = False
    taskId: str = ""
    contextId: str = ""
    task: Optional[AgentTask] = None
    status: Optional[TaskState] = None
