"""
Smart contract ABIs and interfaces for ERC-8004.
"""

from typing import Dict, List, Any

# ERC-721 ABI (minimal required functions)
ERC721_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "ownerOf",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "operator", "type": "address"}
        ],
        "name": "isApprovedForAll",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "getApproved",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "from", "type": "address"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"}
        ],
        "name": "transferFrom",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "bool", "name": "approved", "type": "bool"}
        ],
        "name": "setApprovalForAll",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "address", "name": "to", "type": "address"}
        ],
        "name": "approve",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# ERC-721 URI Storage ABI
ERC721_URI_STORAGE_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "tokenURI",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "string", "name": "_tokenURI", "type": "string"}
        ],
        "name": "setTokenURI",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# Identity Registry ABI
IDENTITY_REGISTRY_ABI = [
    # ERC-721 functions
    *ERC721_ABI,
    *ERC721_URI_STORAGE_ABI,
    
    # Identity Registry specific functions
    {
        "inputs": [],
        "name": "register",
        "outputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "string", "name": "agentURI", "type": "string"}],
        "name": "register",
        "outputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "string", "name": "agentURI", "type": "string"},
            {
                "components": [
                    {"internalType": "string", "name": "key", "type": "string"},
                    {"internalType": "bytes", "name": "value", "type": "bytes"}
                ],
                "internalType": "struct IdentityRegistry.MetadataEntry[]",
                "name": "metadata",
                "type": "tuple[]"
            }
        ],
        "name": "register",
        "outputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "string", "name": "key", "type": "string"}
        ],
        "name": "getMetadata",
        "outputs": [{"internalType": "bytes", "name": "", "type": "bytes"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "string", "name": "key", "type": "string"},
            {"internalType": "bytes", "name": "value", "type": "bytes"}
        ],
        "name": "setMetadata",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "string", "name": "newURI", "type": "string"}
        ],
        "name": "setAgentURI",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"}
        ],
        "name": "getAgentWallet",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "address", "name": "newWallet", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"},
            {"internalType": "bytes", "name": "signature", "type": "bytes"}
        ],
        "name": "setAgentWallet",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    
    # Events
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"indexed": False, "internalType": "string", "name": "agentURI", "type": "string"},
            {"indexed": True, "internalType": "address", "name": "owner", "type": "address"}
        ],
        "name": "Registered",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"indexed": False, "internalType": "string", "name": "newURI", "type": "string"},
            {"indexed": True, "internalType": "address", "name": "updatedBy", "type": "address"}
        ],
        "name": "URIUpdated",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"indexed": True, "internalType": "string", "name": "indexedKey", "type": "string"},
            {"indexed": False, "internalType": "string", "name": "key", "type": "string"},
            {"indexed": False, "internalType": "bytes", "name": "value", "type": "bytes"}
        ],
        "name": "MetadataSet",
        "type": "event"
    }
]

# Reputation Registry ABI
REPUTATION_REGISTRY_ABI = [
    {
        "inputs": [],
        "name": "getIdentityRegistry",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "uint8", "name": "score", "type": "uint8"},
            {"internalType": "string", "name": "tag1", "type": "string"},
            {"internalType": "string", "name": "tag2", "type": "string"},
            {"internalType": "string", "name": "endpoint", "type": "string"},
            {"internalType": "string", "name": "feedbackURI", "type": "string"},
            {"internalType": "bytes32", "name": "feedbackHash", "type": "bytes32"}
        ],
        "name": "giveFeedback",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "uint64", "name": "feedbackIndex", "type": "uint64"}
        ],
        "name": "revokeFeedback",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "address", "name": "clientAddress", "type": "address"},
            {"internalType": "uint64", "name": "feedbackIndex", "type": "uint64"},
            {"internalType": "string", "name": "responseURI", "type": "string"},
            {"internalType": "bytes32", "name": "responseHash", "type": "bytes32"}
        ],
        "name": "appendResponse",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "address", "name": "clientAddress", "type": "address"}
        ],
        "name": "getLastIndex",
        "outputs": [{"internalType": "uint64", "name": "", "type": "uint64"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "address", "name": "clientAddress", "type": "address"},
            {"internalType": "uint64", "name": "feedbackIndex", "type": "uint64"}
        ],
        "name": "readFeedback",
        "outputs": [
            {"internalType": "uint8", "name": "score", "type": "uint8"},
            {"internalType": "string", "name": "tag1", "type": "string"},
            {"internalType": "string", "name": "tag2", "type": "string"},
            {"internalType": "bool", "name": "isRevoked", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "address[]", "name": "clientAddresses", "type": "address[]"},
            {"internalType": "string", "name": "tag1", "type": "string"},
            {"internalType": "string", "name": "tag2", "type": "string"}
        ],
        "name": "getSummary",
        "outputs": [
            {"internalType": "uint64", "name": "count", "type": "uint64"},
            {"internalType": "uint8", "name": "averageScore", "type": "uint8"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "address[]", "name": "clientAddresses", "type": "address[]"},
            {"internalType": "string", "name": "tag1", "type": "string"},
            {"internalType": "string", "name": "tag2", "type": "string"},
            {"internalType": "bool", "name": "includeRevoked", "type": "bool"}
        ],
        "name": "readAllFeedback",
        "outputs": [
            {"internalType": "address[]", "name": "clientAddresses", "type": "address[]"},
            {"internalType": "uint64[]", "name": "feedbackIndexes", "type": "uint64[]"},
            {"internalType": "uint8[]", "name": "scores", "type": "uint8[]"},
            {"internalType": "string[]", "name": "tag1s", "type": "string[]"},
            {"internalType": "string[]", "name": "tag2s", "type": "string[]"},
            {"internalType": "bool[]", "name": "revokedStatuses", "type": "bool[]"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
        "name": "getClients",
        "outputs": [{"internalType": "address[]", "name": "", "type": "address[]"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "address", "name": "clientAddress", "type": "address"},
            {"internalType": "uint64", "name": "feedbackIndex", "type": "uint64"},
            {"internalType": "address[]", "name": "responders", "type": "address[]"}
        ],
        "name": "getResponseCount",
        "outputs": [{"internalType": "uint64", "name": "count", "type": "uint64"}],
        "stateMutability": "view",
        "type": "function"
    },
    
    # Events
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "clientAddress", "type": "address"},
            {"indexed": False, "internalType": "uint64", "name": "feedbackIndex", "type": "uint64"},
            {"indexed": False, "internalType": "uint8", "name": "score", "type": "uint8"},
            {"indexed": True, "internalType": "string", "name": "tag1", "type": "string"},
            {"indexed": False, "internalType": "string", "name": "tag2", "type": "string"},
            {"indexed": False, "internalType": "string", "name": "endpoint", "type": "string"},
            {"indexed": False, "internalType": "string", "name": "feedbackURI", "type": "string"},
            {"indexed": False, "internalType": "bytes32", "name": "feedbackHash", "type": "bytes32"}
        ],
        "name": "NewFeedback",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "clientAddress", "type": "address"},
            {"indexed": True, "internalType": "uint64", "name": "feedbackIndex", "type": "uint64"}
        ],
        "name": "FeedbackRevoked",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "clientAddress", "type": "address"},
            {"indexed": True, "internalType": "uint64", "name": "feedbackIndex", "type": "uint64"},
            {"indexed": True, "internalType": "address", "name": "responder", "type": "address"},
            {"indexed": False, "internalType": "string", "name": "responseURI", "type": "string"}
        ],
        "name": "ResponseAppended",
        "type": "event"
    }
]

# Validation Registry ABI
VALIDATION_REGISTRY_ABI = [
    {
        "inputs": [],
        "name": "getIdentityRegistry",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "validatorAddress", "type": "address"},
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "string", "name": "requestUri", "type": "string"},
            {"internalType": "bytes32", "name": "requestHash", "type": "bytes32"}
        ],
        "name": "validationRequest",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "requestHash", "type": "bytes32"},
            {"internalType": "uint8", "name": "response", "type": "uint8"},
            {"internalType": "string", "name": "responseURI", "type": "string"},
            {"internalType": "bytes32", "name": "responseHash", "type": "bytes32"},
            {"internalType": "string", "name": "tag", "type": "string"}
        ],
        "name": "validationResponse",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "requestHash", "type": "bytes32"}],
        "name": "getValidationStatus",
        "outputs": [
            {"internalType": "address", "name": "validatorAddress", "type": "address"},
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "uint8", "name": "response", "type": "uint8"},
            {"internalType": "string", "name": "tag", "type": "string"},
            {"internalType": "uint256", "name": "lastUpdate", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "address[]", "name": "validatorAddresses", "type": "address[]"},
            {"internalType": "string", "name": "tag", "type": "string"}
        ],
        "name": "getSummary",
        "outputs": [
            {"internalType": "uint64", "name": "count", "type": "uint64"},
            {"internalType": "uint8", "name": "averageResponse", "type": "uint8"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
        "name": "getAgentValidations",
        "outputs": [{"internalType": "bytes32[]", "name": "", "type": "bytes32[]"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "validatorAddress", "type": "address"}],
        "name": "getValidatorRequests",
        "outputs": [{"internalType": "bytes32[]", "name": "", "type": "bytes32[]"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "name": "validations",
        "outputs": [
            {"internalType": "address", "name": "validatorAddress", "type": "address"},
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "uint8", "name": "response", "type": "uint8"},
            {"internalType": "string", "name": "tag", "type": "string"},
            {"internalType": "uint256", "name": "lastUpdate", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    
    # Events
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "validatorAddress", "type": "address"},
            {"indexed": True, "internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"indexed": False, "internalType": "string", "name": "requestUri", "type": "string"},
            {"indexed": True, "internalType": "bytes32", "name": "requestHash", "type": "bytes32"}
        ],
        "name": "ValidationRequest",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "validatorAddress", "type": "address"},
            {"indexed": True, "internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"indexed": True, "internalType": "bytes32", "name": "requestHash", "type": "bytes32"},
            {"indexed": False, "internalType": "uint8", "name": "response", "type": "uint8"},
            {"indexed": False, "internalType": "string", "name": "responseURI", "type": "string"},
            {"indexed": False, "internalType": "bytes32", "name": "responseHash", "type": "bytes32"},
            {"indexed": False, "internalType": "string", "name": "tag", "type": "string"}
        ],
        "name": "ValidationResponse",
        "type": "event"
    }
]

# Contract registry for different chains
# Updated addresses from: https://github.com/erc-8004/erc-8004-contracts
DEFAULT_REGISTRIES: Dict[int, Dict[str, str]] = {
    11155111: {  # Ethereum Sepolia
        "IDENTITY": "0x8004A818BFB912233c491871b3d84c89A494BD9e",
        "REPUTATION": "0x8004B663056A597Dffe9eCcC1965A193B7388713",
        # "VALIDATION": "0x...",  # To be deployed
    },
    # Other chains temporarily disabled - addresses to be deployed
    # 84532: {  # Base Sepolia
    #     "IDENTITY": "0x...",  # To be deployed
    #     "REPUTATION": "0x...",  # To be deployed
    #     "VALIDATION": "0x...",  # To be deployed
    # },
    # 80002: {  # Polygon Amoy
    #     "IDENTITY": "0x...",  # To be deployed
    #     "REPUTATION": "0x...",  # To be deployed
    #     "VALIDATION": "0x...",  # To be deployed
    # },
    # 59141: {  # Linea Sepolia
    #     "IDENTITY": "0x...",  # To be deployed
    #     "REPUTATION": "0x...",  # To be deployed
    #     "VALIDATION": "0x...",  # To be deployed
    # },
}

# Default subgraph URLs for different chains
# Note: Subgraph URLs may need to be updated when new contracts are deployed
DEFAULT_SUBGRAPH_URLS: Dict[int, str] = {
    11155111: "https://gateway.thegraph.com/api/00a452ad3cd1900273ea62c1bf283f93/subgraphs/id/6wQRC7geo9XYAhckfmfo8kbMRLeWU8KQd3XsJqFKmZLT",  # Ethereum Sepolia
    # Other chains temporarily disabled - subgraphs to be updated
    # 84532: "https://gateway.thegraph.com/api/...",  # Base Sepolia - To be updated
    # 80002: "https://gateway.thegraph.com/api/...",  # Polygon Amoy - To be updated
}
