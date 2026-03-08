"""
Shared configuration loader for test examples.
Loads configuration from environment variables (.env file).
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
# Look for .env in project root (agent0-py directory)
# Try parent.parent first (agent0-py/.env), then parent.parent.parent as fallback
env_path = Path(__file__).parent.parent / ".env"
if not env_path.exists():
    env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Chain Configuration
CHAIN_ID = int(os.getenv("CHAIN_ID", "11155111"))
RPC_URL = os.getenv(
    "RPC_URL",
    "https://eth-sepolia.g.alchemy.com/v2/7nkA4bJ0tKWcl2-5Wn15c5eRdpGZ8DDr"
)
AGENT_PRIVATE_KEY = os.getenv("AGENT_PRIVATE_KEY", "")

# IPFS Configuration (Pinata)
PINATA_JWT = os.getenv("PINATA_JWT", "")

# Subgraph Configuration
SUBGRAPH_URL = os.getenv(
    "SUBGRAPH_URL",
    "https://gateway.thegraph.com/api/00a452ad3cd1900273ea62c1bf283f93/subgraphs/id/6wQRC7geo9XYAhckfmfo8kbMRLeWU8KQd3XsJqFKmZLT"
)

# Agent ID for testing (can be overridden via env)
AGENT_ID = os.getenv("AGENT_ID", "11155111:46")

# Client Private Key (for feedback tests - different wallet from agent)
CLIENT_PRIVATE_KEY = os.getenv("CLIENT_PRIVATE_KEY", "")

# Telemetry (for SDK integration tests; after running dashboard seed seed-telemetry-test-user.sql)
AGENT0_API_KEY = os.getenv("AGENT0_API_KEY", "")
AGENT0_TELEMETRY_ENDPOINT = os.getenv("AGENT0_TELEMETRY_ENDPOINT", "")

# Supabase (for telemetry DB assertions; use local from supabase start)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def print_config():
    """Print current configuration (hiding sensitive values)."""
    print("Configuration:")
    print(f"  CHAIN_ID: {CHAIN_ID}")
    print(f"  RPC_URL: {RPC_URL[:50]}...")
    print(f"  AGENT_PRIVATE_KEY: {'***' if AGENT_PRIVATE_KEY else 'NOT SET'}")
    print(f"  CLIENT_PRIVATE_KEY: {'***' if CLIENT_PRIVATE_KEY else 'NOT SET'}")
    print(f"  PINATA_JWT: {'***' if PINATA_JWT else 'NOT SET'}")
    print(f"  SUBGRAPH_URL: {SUBGRAPH_URL[:50]}...")
    print(f"  AGENT_ID: {AGENT_ID}")
    print(f"  AGENT0_API_KEY: {'***' if AGENT0_API_KEY else 'NOT SET'}")
    print(f"  AGENT0_TELEMETRY_ENDPOINT: {AGENT0_TELEMETRY_ENDPOINT or '(default)'}")
    print(f"  SUPABASE_URL: {'***' if SUPABASE_URL else 'NOT SET'}")
    print(f"  SUPABASE_SERVICE_ROLE_KEY: {'***' if SUPABASE_SERVICE_ROLE_KEY else 'NOT SET'}")
    print()

