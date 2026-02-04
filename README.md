# Agent0 SDK

Python SDK for agent portability, discovery and trust based on ERC-8004.

Agent0 is the SDK for agentic economies. It enables agents to register, advertise their capabilities and how to communicate with them, and give each other feedback and reputation signals. All this using blockchain infrastructure (ERC-8004) and decentralized storage, enabling permissionless discovery without relying on proprietary catalogues or intermediaries.

## What Does Agent0 SDK Do?

Agent0 SDK enables you to:

- **Create and manage agent identities** - Register your AI agent on-chain with a unique identity, configure presentation fields (name, description, image), set wallet addresses, and manage trust models with x402 support
- **Advertise agent capabilities** - Publish MCP and A2A endpoints, with automated extraction of MCP tools and A2A skills from endpoints
- **OASF taxonomies** - Advertise standardized skills and domains using the Open Agentic Schema Framework (OASF) taxonomies for better discovery and interoperability
- **Enable permissionless discovery** - Make your agent discoverable by other agents and platforms using rich search by attributes, capabilities, skills, tools, tasks, and x402 support
- **Build reputation** - Give and receive feedback, retrieve feedback history, and search agents by reputation with cryptographic authentication
- **Cross-chain registration** - One-line registration with IPFS nodes, Pinata, Filecoin, or HTTP URIs
- **Public indexing** - Subgraph indexing both on-chain and IPFS data for fast search and retrieval

**Bug reports & feedback:** GitHub: [Report issues](https://github.com/agent0lab/agent0-py/issues) | Telegram: [Agent0 channel](https://t.me/agent0kitchen) | Email: team@ag0.xyz

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager
- Private key for signing transactions (or run in read-only mode)
- Access to an Ethereum RPC endpoint (e.g., Alchemy, Infura)
- (Optional) IPFS provider account (Pinata, Filecoin, or local IPFS node)

### Install from PyPI

```bash
pip install agent0-sdk
```

To install the **1.5.1 pre-release** explicitly:

```bash
pip install --pre agent0-sdk==1.5.1b1
```

### Install from Source

```bash
git clone https://github.com/agent0lab/agent0-py.git
cd agent0-py
pip install -e .
```

## Quick Start

### 1. Initialize SDK

```python
from agent0_sdk import SDK
import os

# Initialize SDK with IPFS and subgraph
sdk = SDK(
    chainId=11155111,  # Ethereum Sepolia testnet (use 1 for Ethereum Mainnet)
    rpcUrl=os.getenv("RPC_URL"),
    signer=os.getenv("PRIVATE_KEY"),
    ipfs="pinata",  # Options: "pinata", "filecoinPin", "node"
    pinataJwt=os.getenv("PINATA_JWT")  # For Pinata
    # Subgraph URL auto-defaults from DEFAULT_SUBGRAPH_URLS
)
```

### 2. Create and Register Agent

```python
# Create agent
agent = sdk.createAgent(
    name="My AI Agent",
    description="An intelligent assistant for various tasks. Skills: data analysis, code generation.",
    image="https://example.com/agent-image.png"
)

# Configure endpoints (automatically extracts capabilities)
agent.setMCP("https://mcp.example.com/")  # Extracts tools, prompts, resources
agent.setA2A("https://a2a.example.com/agent-card.json")  # Extracts skills
agent.setENS("myagent.eth")

# Add OASF skills and domains (standardized taxonomies)
agent.addSkill("data_engineering/data_transformation_pipeline", validate_oasf=True)
agent.addSkill("natural_language_processing/natural_language_generation/summarization", validate_oasf=True)
agent.addDomain("finance_and_business/investment_services", validate_oasf=True)
agent.addDomain("technology/data_science/data_science", validate_oasf=True)

agent.setTrust(reputation=True, cryptoEconomic=True)

# Add metadata and set status
agent.setMetadata({"version": "1.0.0", "category": "ai-assistant"})
agent.setActive(True)

# Register on-chain with IPFS (submitted-by-default)
reg_tx = agent.registerIPFS()
reg = reg_tx.wait_confirmed(timeout=180).result
print(f"Agent registered: {reg.agentId}")  # e.g., "11155111:123"
print(f"Agent URI: {reg.agentURI}")  # e.g., "ipfs://Qm..."

# (Optional) Change the agent wallet after registration
# - On mint/registration, `agentWallet` defaults to the current owner address.
# - Call this only if you want a DIFFERENT wallet (or after a transfer, since the wallet resets to zero).
# - Transaction is sent by the SDK signer (agent owner), but the signature must be produced by the NEW wallet.
wallet_tx = agent.setWallet(
    "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
    chainId=11155111,
    new_wallet_signer=os.getenv("NEW_WALLET_PRIVATE_KEY"),
)
if wallet_tx:
    wallet_tx.wait_confirmed(timeout=180)
```

### 3. Load and Edit Agent

```python
# Load existing agent for editing
agent = sdk.loadAgent("11155111:123")  # Format: "chainId:agentId"

# Edit agent properties
agent.updateInfo(description="Updated description with new capabilities")
agent.setMCP("https://new-mcp.example.com/")

# Re-register to update on-chain
update_tx = agent.registerIPFS()
update = update_tx.wait_confirmed(timeout=180).result
print(f"Updated: {update.agentURI}")
```

### 4. Search Agents

```python
# Search by name, capabilities, or attributes
results = sdk.searchAgents(
    filters={
        "name": "AI",  # substring
        "mcpTools": ["code_generation"],
        "a2aSkills": ["python"],
        "active": True,
        "x402support": True,
        "feedback": {"minValue": 80, "tag": "enterprise", "includeRevoked": False},
    },
    options={"sort": ["updatedAt:desc"]},
)

for agent in results:
    print(f"{agent.name}: {agent.description}")
    print(f"  Tools: {agent.mcpTools}")
    print(f"  Skills: {agent.a2aSkills}")

# Get single agent (read-only, faster)
agent_summary = sdk.getAgent("11155111:123")
```

### 5. Give and Retrieve Feedback

```python
# On-chain-only feedback (no off-chain upload, even if IPFS is configured)
tx = sdk.giveFeedback(
    agentId="11155111:123",
    value=85,  # number|string
    tag1="data_analyst",  # Optional: tags are strings
    tag2="finance",
    endpoint="https://example.com/endpoint",  # Optional: saved on-chain
)
feedback = tx.wait_confirmed(timeout=180).result

# Rich feedback (optional off-chain file + on-chain fields)
feedback_file = sdk.prepareFeedbackFile({
    "capability": "tools",       # Optional: MCP capability
    "name": "code_generation",   # Optional: MCP tool name
    "skill": "python",           # Optional: A2A skill
    "text": "Great agent!",      # Optional
})

tx = sdk.giveFeedback(
    agentId="11155111:123",
    value=85,
    tag1="data_analyst",
    tag2="finance",
    endpoint="https://example.com/endpoint",
    feedbackFile=feedback_file,  # If provided, requires IPFS configured
)
feedback = tx.wait_confirmed(timeout=180).result

# Search feedback
results = sdk.searchFeedback(
    agentId="11155111:123",
    capabilities=["tools"],
    minValue=80,
    maxValue=100
)

# NEW: Search feedback given by a reviewer wallet (across all agents; subgraph required)
given = sdk.searchFeedback(
    reviewers=["0x742d35cc6634c0532925a3b844bc9e7595f0beb7"]
)

# NEW: Search feedback across multiple agents at once
multi = sdk.searchFeedback(
    agents=["11155111:123", "11155111:456", "11155111:789"]
)

# Get reputation summary
summary = sdk.getReputationSummary("11155111:123")
print(f"Average value: {summary['averageValue']}")
```

## IPFS Configuration Options

```python
# Option 1: Filecoin Pin (free for ERC-8004 agents)
sdk = SDK(
    chainId=11155111,
    rpcUrl="...",
    signer=private_key,
    ipfs="filecoinPin",
    filecoinPrivateKey="your-filecoin-private-key"
)

# Option 2: IPFS Node
sdk = SDK(
    chainId=11155111,
    rpcUrl="...",
    signer=private_key,
    ipfs="node",
    ipfsNodeUrl="https://ipfs.infura.io:5001"
)

# Option 3: Pinata (free for ERC-8004 agents)
sdk = SDK(
    chainId=11155111,
    rpcUrl="...",
    signer=private_key,
    ipfs="pinata",
    pinataJwt="your-pinata-jwt-token"
)

# Option 4: HTTP registration (no IPFS)
sdk = SDK(chainId=11155111, rpcUrl="...", signer=private_key)
agent.register("https://example.com/agent-registration.json")
```

## OASF Taxonomies

The SDK includes support for the **Open Agentic Schema Framework (OASF)** taxonomies, enabling agents to advertise standardized skills and domains. This improves discoverability and interoperability across agent platforms.

### Adding Skills and Domains

```python
# Add OASF skills (with optional validation)
agent.addSkill("advanced_reasoning_planning/strategic_planning", validate_oasf=True)
agent.addSkill("data_engineering/data_transformation_pipeline", validate_oasf=True)

# Add OASF domains (with optional validation)
agent.addDomain("finance_and_business/investment_services", validate_oasf=True)
agent.addDomain("technology/data_science/data_visualization", validate_oasf=True)

# Remove skills/domains
agent.removeSkill("old_skill")
agent.removeDomain("old_domain")
```

### OASF in Registration Files

OASF skills and domains appear in your agent's registration file:

```json
{
  "endpoints": [
    {
      "name": "OASF",
      "endpoint": "https://github.com/agntcy/oasf/",
      "version": "0.8",
      "skills": [
        "advanced_reasoning_planning/strategic_planning",
        "data_engineering/data_transformation_pipeline"
      ],
      "domains": [
        "finance_and_business/investment_services",
        "technology/data_science/data_science"
      ]
    }
  ]
}
```

### Taxonomy Files

The SDK includes complete OASF v0.8.0 taxonomy files:
- **Skills**: `agent0_sdk/taxonomies/all_skills.json` (136 skills)
- **Domains**: `agent0_sdk/taxonomies/all_domains.json` (204 domains)

Browse these files to find appropriate skill and domain slugs. For more information, see the [OASF specification](https://github.com/agntcy/oasf) and [Release Notes v0.31](RELEASE_NOTES_0.31.md).

## Unified Search Reference (Exhaustive)

The unified search API is:

```python
results = sdk.searchAgents(filters: dict | SearchFilters | None = None, options: dict | SearchOptions | None = None)
# results: list[AgentSummary]
```

### `FeedbackFilters` (used as `filters["feedback"]`)

```python
@dataclass
class FeedbackFilters:
    hasFeedback: Optional[bool] = None
    hasNoFeedback: Optional[bool] = None
    includeRevoked: Optional[bool] = None
    minValue: Optional[float] = None
    maxValue: Optional[float] = None
    minCount: Optional[int] = None
    maxCount: Optional[int] = None
    fromReviewers: Optional[List[Address]] = None
    endpoint: Optional[str] = None          # substring match
    hasResponse: Optional[bool] = None
    tag1: Optional[str] = None
    tag2: Optional[str] = None
    tag: Optional[str] = None               # matches tag1 OR tag2
```

| Field | Semantics |
| --- | --- |
| `hasFeedback` / `hasNoFeedback` | Filter by whether the agent has any feedback |
| `includeRevoked` | Include revoked feedback entries in the pool used for filtering |
| `minValue` / `maxValue` | Threshold on **average value** over feedback matching the other feedback constraints (inclusive) |
| `minCount` / `maxCount` | Threshold on **count** over feedback matching the other feedback constraints (inclusive) |
| `fromReviewers` | Only consider feedback from these reviewer wallets |
| `endpoint` | Only consider feedback whose `endpoint` contains this substring |
| `hasResponse` | Only consider feedback that has at least one response (if supported) |
| `tag1` / `tag2` | Only consider feedback matching tag1/tag2 |
| `tag` | Shorthand: match either tag1 OR tag2 |

### `SearchFilters`

```python
DateLike = Union[datetime, str, int]

@dataclass
class SearchFilters:
    chains: Optional[Union[List[ChainId], Literal["all"]]] = None
    agentIds: Optional[List[AgentId]] = None

    name: Optional[str] = None
    description: Optional[str] = None

    owners: Optional[List[Address]] = None
    operators: Optional[List[Address]] = None

    hasRegistrationFile: Optional[bool] = None
    hasWeb: Optional[bool] = None
    hasMCP: Optional[bool] = None
    hasA2A: Optional[bool] = None
    hasOASF: Optional[bool] = None
    hasEndpoints: Optional[bool] = None

    webContains: Optional[str] = None
    mcpContains: Optional[str] = None
    a2aContains: Optional[str] = None
    ensContains: Optional[str] = None
    didContains: Optional[str] = None

    walletAddress: Optional[Address] = None

    supportedTrust: Optional[List[str]] = None
    a2aSkills: Optional[List[str]] = None
    mcpTools: Optional[List[str]] = None
    mcpPrompts: Optional[List[str]] = None
    mcpResources: Optional[List[str]] = None
    oasfSkills: Optional[List[str]] = None
    oasfDomains: Optional[List[str]] = None

    active: Optional[bool] = None
    x402support: Optional[bool] = None

    registeredAtFrom: Optional[DateLike] = None
    registeredAtTo: Optional[DateLike] = None
    updatedAtFrom: Optional[DateLike] = None
    updatedAtTo: Optional[DateLike] = None

    hasMetadataKey: Optional[str] = None
    metadataValue: Optional[Dict[str, str]] = None  # { key, value }

    keyword: Optional[str] = None
    feedback: Optional[FeedbackFilters] = None
```

### `SearchOptions`

```python
@dataclass
class SearchOptions:
    sort: Optional[List[str]] = None
    semanticMinScore: Optional[float] = None
    semanticTopK: Optional[int] = None
```

### `AgentSummary` (returned items)

```python
@dataclass
class AgentSummary:
    chainId: ChainId
    agentId: AgentId
    name: str
    image: Optional[URI]
    description: str
    owners: List[Address]
    operators: List[Address]
    # Endpoint strings (present when advertised; not booleans)
    mcp: Optional[str] = None
    a2a: Optional[str] = None
    web: Optional[str] = None
    email: Optional[str] = None
    ens: Optional[str] = None
    did: Optional[str] = None
    walletAddress: Optional[Address] = None
    supportedTrusts: List[str] = field(default_factory=list)
    a2aSkills: List[str] = field(default_factory=list)
    mcpTools: List[str] = field(default_factory=list)
    mcpPrompts: List[str] = field(default_factory=list)
    mcpResources: List[str] = field(default_factory=list)
    oasfSkills: List[str] = field(default_factory=list)
    oasfDomains: List[str] = field(default_factory=list)
    active: bool = False
    x402support: bool = False
    createdAt: Optional[int] = None
    updatedAt: Optional[int] = None
    lastActivity: Optional[int] = None
    agentURI: Optional[str] = None
    agentURIType: Optional[str] = None
    feedbackCount: Optional[int] = None
    averageValue: Optional[float] = None
    semanticScore: Optional[float] = None
    extras: Dict[str, Any] = field(default_factory=dict)
```

## Use Cases

- **Building agent marketplaces** - Create platforms where developers can discover, evaluate, and integrate agents based on their capabilities and reputation
- **Agent interoperability** - Discover agents by specific capabilities (skills, tools, tasks), evaluate them through reputation signals, and integrate them via standard protocols (MCP/A2A)
- **Managing agent reputation** - Track agent performance, collect feedback from users and other agents, and build trust signals for your agent ecosystem
- **Cross-chain agent operations** - Deploy and manage agents across multiple blockchain networks with consistent identity and reputation

## 🚀 Coming Soon

- More chains (currently Ethereum Mainnet + Ethereum Sepolia + Polygon Mainnet)
- Support for validations
- Enhanced x402 payments
- Advanced reputation aggregation
- Import/Export to centralized catalogues

## Tests

Complete working examples are available in the `tests/` directory:

- `test_registration.py` - Agent registration with HTTP URI
- `test_registrationIpfs.py` - Agent registration with IPFS
- `test_feedback.py` - Complete feedback flow with IPFS storage
- `test_search.py` - Agent search and discovery
- `test_transfer.py` - Agent ownership transfer
- `test_oasf_management.py` - OASF skills/domains management (unit tests)
- `test_real_public_servers.py` - Endpoint crawler against real public MCP/A2A servers
- `test_multi_chain.py` - Multi-chain read-only operations (subgraph-based)

## Documentation

Full documentation is available at [sdk.ag0.xyz](https://sdk.ag0.xyz), including:

- [Installation Guide](https://sdk.ag0.xyz/2-usage/2-1-install/)
- [Agent Configuration](https://sdk.ag0.xyz/2-usage/2-2-configure-agents/)
- [Registration](https://sdk.ag0.xyz/2-usage/2-3-registration-ipfs/)
- [Search](https://sdk.ag0.xyz/2-usage/2-5-search/)
- [Feedback](https://sdk.ag0.xyz/2-usage/2-6-use-feedback/)
- [Key Concepts](https://sdk.ag0.xyz/1-welcome/1-2-key-concepts/)
- [API Reference](https://sdk.ag0.xyz/5-reference/5-1-sdk/)

## License

Agent0 SDK is MIT-licensed public good brought to you by Marco De Rossi in collaboration with Consensys, 🦊 MetaMask and Agent0, Inc. We are looking for co-maintainers. Please reach out if you want to help.

Thanks also to Edge & Node (The Graph), Protocol Labs and Pinata for their support.
