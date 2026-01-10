"""
Web3 integration layer for smart contract interactions.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple, Union, Callable

try:
    from web3 import Web3
    from web3.contract import Contract
    from eth_account import Account
    from eth_account.signers.base import BaseAccount
except ImportError:
    raise ImportError(
        "Web3 dependencies not installed. Install with: pip install web3 eth-account"
    )


class Web3Client:
    """Web3 client for interacting with ERC-8004 smart contracts."""

    def __init__(
        self,
        rpc_url: str,
        private_key: Optional[str] = None,
        account: Optional[BaseAccount] = None,
    ):
        """Initialize Web3 client."""
        self.rpc_url = rpc_url
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError("Failed to connect to Ethereum node")
        
        if account:
            self.account = account
        elif private_key:
            self.account = Account.from_key(private_key)
        else:
            # Read-only mode - no account
            self.account = None
        
        self.chain_id = self.w3.eth.chain_id

    def get_contract(self, address: str, abi: List[Dict[str, Any]]) -> Contract:
        """Get contract instance."""
        return self.w3.eth.contract(address=address, abi=abi)

    def call_contract(
        self,
        contract: Contract,
        method_name: str,
        *args,
        **kwargs
    ) -> Any:
        """Call a contract method (view/pure)."""
        method = getattr(contract.functions, method_name)
        return method(*args, **kwargs).call()

    def transact_contract(
        self,
        contract: Contract,
        method_name: str,
        *args,
        gas_limit: Optional[int] = None,
        gas_price: Optional[int] = None,
        max_fee_per_gas: Optional[int] = None,
        max_priority_fee_per_gas: Optional[int] = None,
        **kwargs
    ) -> str:
        """Execute a contract transaction."""
        if not self.account:
            raise ValueError("Cannot execute transaction: SDK is in read-only mode. Provide a signer to enable write operations.")
        
        method = getattr(contract.functions, method_name)
        
        # Build transaction with proper nonce management
        # Use 'pending' to get the next nonce including pending transactions
        nonce = self.w3.eth.get_transaction_count(self.account.address, 'pending')
        tx = method(*args, **kwargs).build_transaction({
            'from': self.account.address,
            'nonce': nonce,
        })
        
        # Add gas settings
        if gas_limit:
            tx['gas'] = gas_limit
        if gas_price:
            tx['gasPrice'] = gas_price
        if max_fee_per_gas:
            tx['maxFeePerGas'] = max_fee_per_gas
        if max_priority_fee_per_gas:
            tx['maxPriorityFeePerGas'] = max_priority_fee_per_gas
        
        # Sign and send
        signed_tx = self.w3.eth.account.sign_transaction(tx, self.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction if hasattr(signed_tx, 'rawTransaction') else signed_tx.raw_transaction)
        
        return tx_hash.hex()

    def wait_for_transaction(self, tx_hash: str, timeout: int = 60) -> Dict[str, Any]:
        """Wait for transaction to be mined."""
        return self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

    def get_events(
        self,
        contract: Contract,
        event_name: str,
        from_block: int = 0,
        to_block: Optional[int] = None,
        argument_filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Get contract events."""
        if to_block is None:
            to_block = self.w3.eth.block_number
        
        event_filter = contract.events[event_name].create_filter(
            fromBlock=from_block,
            toBlock=to_block,
            argument_filters=argument_filters or {}
        )
        
        return event_filter.get_all_entries()

    def signMessage(self, message: bytes) -> bytes:
        """Sign a message with the account's private key."""
        # Create a SignableMessage from the raw bytes
        from eth_account.messages import encode_defunct
        signableMessage = encode_defunct(message)
        signedMessage = self.account.sign_message(signableMessage)
        return signedMessage.signature

    def recoverAddress(self, message: bytes, signature: bytes) -> str:
        """Recover address from message and signature."""
        from eth_account.messages import encode_defunct
        signable_message = encode_defunct(message)
        return self.w3.eth.account.recover_message(signable_message, signature=signature)

    def keccak256(self, data: bytes) -> bytes:
        """Compute Keccak-256 hash."""
        return self.w3.keccak(data)

    def to_checksum_address(self, address: str) -> str:
        """Convert address to checksum format."""
        return self.w3.to_checksum_address(address)
    
    def normalize_address(self, address: str) -> str:
        """Normalize address to lowercase for consistent storage and comparison.
        
        Ethereum addresses are case-insensitive but EIP-55 checksum addresses
        use mixed case. For storage and comparison purposes, we normalize to
        lowercase to avoid case-sensitivity issues.
        
        Args:
            address: Ethereum address (with or without checksum)
            
        Returns:
            Address in lowercase format
        """
        # Remove 0x prefix if present, convert to lowercase, re-add prefix
        if address.startswith("0x") or address.startswith("0X"):
            return "0x" + address[2:].lower()
        return address.lower()

    def is_address(self, address: str) -> bool:
        """Check if string is a valid Ethereum address."""
        return self.w3.is_address(address)

    def get_balance(self, address: str) -> int:
        """Get ETH balance of an address."""
        return self.w3.eth.get_balance(address)

    def get_transaction_count(self, address: str) -> int:
        """Get transaction count (nonce) of an address."""
        return self.w3.eth.get_transaction_count(address)

    def encodeEIP712Domain(
        self,
        name: str,
        version: str,
        chain_id: int,
        verifying_contract: str
    ) -> Dict[str, Any]:
        """Encode EIP-712 domain separator.
        
        Args:
            name: Contract name
            version: Contract version
            chain_id: Chain ID
            verifying_contract: Contract address
            
        Returns:
            Domain separator dictionary
        """
        return {
            "name": name,
            "version": version,
            "chainId": chain_id,
            "verifyingContract": verifying_contract
        }

    def build_agent_wallet_set_typed_data(
        self,
        agent_id: int,
        new_wallet: str,
        owner: str,
        deadline: int,
        verifying_contract: str,
        chain_id: int,
    ) -> Dict[str, Any]:
        """Build EIP-712 typed data for ERC-8004 IdentityRegistry setAgentWallet.

        Contract expects:
        - domain: name="ERC8004IdentityRegistry", version="1"
        - primaryType: "AgentWalletSet"
        - message: { agentId, newWallet, owner, deadline }
        """
        domain = self.encodeEIP712Domain(
            name="ERC8004IdentityRegistry",
            version="1",
            chain_id=chain_id,
            verifying_contract=verifying_contract,
        )

        message_types = {
            "AgentWalletSet": [
                {"name": "agentId", "type": "uint256"},
                {"name": "newWallet", "type": "address"},
                {"name": "owner", "type": "address"},
                {"name": "deadline", "type": "uint256"},
            ]
        }

        message = {
            "agentId": agent_id,
            "newWallet": new_wallet,
            "owner": owner,
            "deadline": deadline,
        }

        # eth_account.messages.encode_typed_data expects the "full_message" format
        return {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                **message_types,
            },
            "domain": domain,
            "primaryType": "AgentWalletSet",
            "message": message,
        }

    def sign_typed_data(
        self,
        full_message: Dict[str, Any],
        signer: Union[str, BaseAccount],
    ) -> bytes:
        """Sign EIP-712 typed data with a provided signer (EOA).

        Args:
            full_message: Typed data dict compatible with encode_typed_data(full_message=...)
            signer: Private key string or eth_account BaseAccount/LocalAccount

        Returns:
            Signature bytes
        """
        from eth_account.messages import encode_typed_data

        if isinstance(signer, str):
            acct: BaseAccount = Account.from_key(signer)
        else:
            acct = signer

        encoded = encode_typed_data(full_message=full_message)
        signed = acct.sign_message(encoded)
        return signed.signature

    def signEIP712Message(
        self,
        domain: Dict[str, Any],
        message_types: Dict[str, List[Dict[str, str]]],
        message: Dict[str, Any]
    ) -> bytes:
        """Sign an EIP-712 typed message.
        
        Args:
            domain: EIP-712 domain separator
            message_types: Type definitions for the message
            message: Message data to sign
            
        Returns:
            Signature bytes
        """
        if not self.account:
            raise ValueError("Cannot sign message: SDK is in read-only mode. Provide a signer to enable signing.")
        
        from eth_account.messages import encode_typed_data
        
        structured_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"}
                ],
                **message_types
            },
            "domain": domain,
            "primaryType": list(message_types.keys())[0] if message_types else "Message",
            "message": message
        }
        
        encoded = encode_typed_data(full_message=structured_data)
        signed = self.account.sign_message(encoded)
        return signed.signature

    def verifyEIP712Signature(
        self,
        domain: Dict[str, Any],
        message_types: Dict[str, List[Dict[str, str]]],
        message: Dict[str, Any],
        signature: bytes
    ) -> str:
        """Verify an EIP-712 signature and recover the signer address.
        
        Args:
            domain: EIP-712 domain separator
            message_types: Type definitions for the message
            message: Message data that was signed
            signature: Signature bytes to verify
            
        Returns:
            Recovered signer address
        """
        from eth_account.messages import encode_typed_data
        
        structured_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"}
                ],
                **message_types
            },
            "domain": domain,
            "primaryType": list(message_types.keys())[0] if message_types else "Message",
            "message": message
        }
        
        encoded = encode_typed_data(full_message=structured_data)
        return self.w3.eth.account.recover_message(encoded, signature=signature)
