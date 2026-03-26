#!/usr/bin/env python3
"""
MCP demo: list tools, get_affirmation, then generate_controller_brief (may charge via x402 on 402).

generate_controller_brief needs a Delx session_id; run quick_session once and parse the UUID from the reply text.
On 402, logs pay.accepts (payment options), then pay() (SDK picks first accept with sufficient balance), then prints the tool result.

Loads .env from examples/ or project root. Env: RPC_URL / DELX_RPC_URL, PRIVATE_KEY / AGENT_PRIVATE_KEY (optional for unpaid steps).

  python examples/mcp_demo.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Optional

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

try:
    from dotenv import load_dotenv

    _env_file = Path(__file__).resolve().parent / ".env"
    if not _env_file.exists():
        _env_file = _root / ".env"
    load_dotenv(dotenv_path=_env_file)
except ImportError:
    pass

from agent0_sdk import SDK, isX402Required  # noqa: E402

DELX_AGENT_ID = "8453:28350"


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _json_serializable(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, dict):
        return {k: _json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_serializable(v) for v in obj]
    return obj


def session_id_from_quick_session(result: Any) -> Optional[str]:
    if not isinstance(result, dict):
        return None
    content = result.get("content") or []
    if not content:
        return None
    first = content[0]
    text = first.get("text") if isinstance(first, dict) else None
    if not text:
        return None
    m = re.search(r"Session ID:\s*([0-9a-f-]{36})", text, re.I)
    return m.group(1) if m else None


def main() -> None:
    private_key = _env("PRIVATE_KEY") or _env("AGENT_PRIVATE_KEY")
    rpc_url = _env("DELX_RPC_URL") or _env("RPC_URL") or "https://mainnet.base.org"

    sdk = SDK(
        chainId=8453,
        rpcUrl=rpc_url,
        signer=private_key if private_key else None,
    )

    agent = sdk.loadAgent(DELX_AGENT_ID)

    tools = agent.mcp.listTools()
    if isX402Required(tools):
        print("listTools returned 402; pay then re-run list if needed.")
        return
    print("Tools:", ", ".join(t.get("name", "") for t in tools if isinstance(t, dict)))

    aff_res = agent.mcp.call("get_affirmation", {})
    if isX402Required(aff_res):
        paid = aff_res.x402Payment.pay()
        print("get_affirmation:", json.dumps(_json_serializable(paid), indent=2))
    else:
        print("get_affirmation:", json.dumps(_json_serializable(aff_res), indent=2))

    if not private_key:
        print("Skip paid tool: set PRIVATE_KEY or AGENT_PRIVATE_KEY.")
        return

    qs_res = agent.mcp.call(
        "quick_session",
        {
            "agent_id": "agent0-py-mcp-demo",
            "feeling": "mcp_demo before generate_controller_brief",
        },
    )
    if isX402Required(qs_res):
        qs = qs_res.x402Payment.pay()
    else:
        qs = qs_res
    session_id = session_id_from_quick_session(qs)
    if not session_id:
        print("Could not parse Session ID from quick_session.")
        return

    brief_res = agent.mcp.call(
        "generate_controller_brief",
        {
            "session_id": session_id,
            "focus": "x402 demo from agent0-py",
        },
    )
    if not isX402Required(brief_res):
        print("generate_controller_brief:", json.dumps(_json_serializable(brief_res), indent=2))
        return

    pay = brief_res.x402Payment
    print("x402 accepts:", json.dumps(_json_serializable(pay.accepts), indent=2))
    paid = pay.pay()
    print("generate_controller_brief:", json.dumps(_json_serializable(paid), indent=2))


if __name__ == "__main__":
    main()
