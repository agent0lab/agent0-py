#!/usr/bin/env python3
"""
x402 and A2A demo: three flows.

1. Pure x402: GET a paid resource with sdk.request() and optional pay.
2. Pure A2A: message, task ops, list_tasks, load_task on loaded agent; use sdk.createA2AClient(summary) when you only have an AgentSummary.
3. A2A + 402: same as (2) when the A2A server returns 402; pay then continue.

Loads env from .env (examples/.env or project root .env). Set PRIVATE_KEY or AGENT_PRIVATE_KEY, RPC_URL.
Use the same key as agent0-ts/examples so both demos use one wallet.
Optional: CHAIN_ID (default 84532), AGENT_ID_PURE_A2A (default 84532:1298),
AGENT_ID_A2A_X402 (default 84532:1301), BASE_MAINNET_RPC_URL, X402_DEMO_URL.
Set X402_DEBUG=1 to print the exact payment payload and server response when debugging 402.
Run: python examples/x402_a2a_demo.py
"""

import os
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

# Add project root for imports when run as script
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

# Load .env from examples/ or project root (requires python-dotenv)
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).resolve().parent / ".env"
    if not _env_file.exists():
        _env_file = _root / ".env"
    load_dotenv(dotenv_path=_env_file)
except ImportError:
    pass  # run without .env; use exported env vars only

from agent0_sdk import SDK


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _json_serializable(obj):
    """Convert result to JSON-serializable form (e.g. dataclass -> dict)."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, dict):
        return {k: _json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_serializable(v) for v in obj]
    return obj


def main() -> None:
    # Same env vars as TS demo: PRIVATE_KEY or AGENT_PRIVATE_KEY so one .env works for both
    private_key = _env("PRIVATE_KEY") or _env("AGENT_PRIVATE_KEY")
    rpc_url = _env("RPC_URL")
    if not private_key or not rpc_url:
        print("Set PRIVATE_KEY (or AGENT_PRIVATE_KEY) and RPC_URL to run this demo.")
        print("Optional: BASE_MAINNET_RPC_URL, OVERRIDE_RPC_URLS (JSON e.g. {\"1\": \"https://...\"})")
        return

    override_rpc = {}
    if _env("OVERRIDE_RPC_URLS"):
        try:
            override_rpc = json.loads(_env("OVERRIDE_RPC_URLS"))
        except json.JSONDecodeError:
            pass
    if _env("BASE_MAINNET_RPC_URL"):
        override_rpc[8453] = _env("BASE_MAINNET_RPC_URL")  # Base mainnet for x402 (match TS; optional override)

    chain_id = int(_env("CHAIN_ID", "84532"))
    sdk = SDK(
        chainId=chain_id,
        rpcUrl=rpc_url,
        signer=private_key,
        overrideRpcUrls=override_rpc if override_rpc else None,
    )

    wa = sdk.web3_client.account.address if sdk.web3_client.account else ""
    print("WA", wa)

    # --- Flow 1: Pure x402 GET ---
    # Default: same x402 API as TS (returns 402; pay with Base USDC). Use X402_DEMO_URL to override.
    x402_url = os.environ.get(
        "X402_DEMO_URL",
        "https://twitter.x402.agentbox.fyi/search?q=from:elonmusk+AI&type=Latest&limit=5",
    )
    print("\n--- 1. Pure x402 ---")
    try:
        if os.environ.get("X402_DEBUG"):
            print("  [X402_DEBUG is set; payment payload and server response will be printed]")
        print("  Sending GET request...")
        result = sdk.request({"url": x402_url, "method": "GET", "headers": {}})
        if getattr(result, "x402Required", False):
            n = len(result.x402Payment.accepts) if result.x402Payment else 0
            print("  Server returned 402 Payment Required.")
            print("  Payment options:", n, "accept(s). Building payment and retrying request...")
            try:
                paid = result.x402Payment.pay()
                print("  Request succeeded after payment.")
                print(json.dumps(_json_serializable(paid), indent=2))
            except Exception as pay_err:
                print("  Error:", pay_err)
                if "402 again" in str(pay_err):
                    print("  Hint: Server rejected the payment (e.g. wallet may need USDC on Base, or check server requirements).")
                    print("  Run with X402_DEBUG=1 to see the exact payload sent and server response.")
        else:
            print("  Request succeeded (2xx). Result:", type(result).__name__, "keys" if isinstance(result, dict) else str(result)[:80])
    except Exception as e:
        print("  Error:", e)

    # --- Flow 2: Pure A2A (load agent by ID, same as TS: 84532:1298) ---
    agent_id_pure = _env("AGENT_ID_PURE_A2A", "84532:1298")
    print("\n--- 2. Pure A2A ---")
    try:
        print("  Loading agent", agent_id_pure, "...")
        agent = sdk.loadAgent(agent_id_pure)
        print("  Sending message...")
        out = agent.messageA2A("Hello, this is a demo message.")
        if getattr(out, "x402Required", False):
            print("  Server returned 402 Payment Required (this agent can charge; see Flow 3).")
        else:
            print("  messageA2A response:", type(out).__name__)
            if hasattr(out, "task") and out.task:
                task = out.task
                print("  Querying task...")
                task.query()
                print("  Sending follow-up message, then cancelling task...")
                task.message("Follow-up message.")
                task.cancel()
                print("  Task cancelled.")
        print("  Listing tasks...")
        tasks = agent.listTasks()
        if getattr(tasks, "x402Required", False):
            print("  listTasks returned 402 Payment Required.")
        else:
            print("  listTasks: count =", len(tasks) if isinstance(tasks, list) else 0)
            if isinstance(tasks, list) and tasks:
                print("  Loading first task and querying...")
                loaded = agent.loadTask(tasks[0].taskId)
                if not getattr(loaded, "x402Required", False):
                    loaded.query()
                    print("  loadTask + query(): ok")
    except Exception as e:
        print("  Error:", e)

    # --- Flow 3: A2A with x402 (agent 84532:1301 returns 402; pay then get response) ---
    agent_id_x402 = _env("AGENT_ID_A2A_X402", "84532:1301")
    print("\n--- 3. A2A with x402 ---")
    try:
        print("  Loading agent", agent_id_x402, "(this agent requires payment)...")
        agent = sdk.loadAgent(agent_id_x402)
        print("  Sending message...")
        result = agent.messageA2A("Hello, please charge me once.")
        if getattr(result, "x402Required", False):
            n = len(result.x402Payment.accepts) if result.x402Payment else 0
            print("  Server returned 402 Payment Required.")
            print("  Payment options:", n, "accept(s). Building payment and retrying...")
            try:
                paid = result.x402Payment.pay()
                print("  Request succeeded after payment. Result:", type(paid).__name__)
            except Exception as pay_err:
                print("  Error:", pay_err)
                if "402 again" in str(pay_err):
                    print("  Hint: Server rejected the payment (e.g. wallet may need sufficient balance on the payment chain).")
        else:
            print("  messageA2A response (2xx):", type(result).__name__)
    except Exception as e:
        print("  Error:", e)

    print("\nDone.")


if __name__ == "__main__":
    main()
