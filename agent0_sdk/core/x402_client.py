"""
x402 micropayment protocol client for agent payments.
Handles USDC payments for agent requests.
"""

import logging
from typing import Optional, Dict, Any
from web3 import Web3
from eth_account import Account
import requests

logger = logging.getLogger(__name__)

# USDC contract addresses
USDC_SEPOLIA = "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238"  # Ethereum Sepolia
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base mainnet
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"  # Base Sepolia

# Minimal ERC20 ABI for approve and transfer
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]


class X402Client:
    """Client for x402 micropayment protocol."""

    def __init__(
        self,
        rpc_url: str,
        private_key: str,
        chain_id: int = 11155111
    ):
        """
        Initialize x402 payment client.

        Args:
            rpc_url: Ethereum RPC URL
            private_key: Private key for signing transactions
            chain_id: Chain ID (default: Sepolia 11155111)
        """
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.chain_id = chain_id

        # Setup account
        if private_key.startswith('0x'):
            private_key = private_key[2:]
        self.account = Account.from_key(private_key)
        self.address = self.account.address

        # Setup USDC contract based on chain
        if chain_id == 8453:  # Base mainnet
            self.usdc_address = Web3.to_checksum_address(USDC_BASE)
        elif chain_id == 84532:  # Base Sepolia
            self.usdc_address = Web3.to_checksum_address(USDC_BASE_SEPOLIA)
        elif chain_id == 11155111:  # Ethereum Sepolia
            self.usdc_address = Web3.to_checksum_address(USDC_SEPOLIA)
        else:
            raise ValueError(f"Unsupported chain ID: {chain_id}. Supported: 8453 (Base), 84532 (Base Sepolia), 11155111 (Ethereum Sepolia)")

        self.usdc = self.w3.eth.contract(
            address=self.usdc_address,
            abi=ERC20_ABI
        )

        logger.info(f"X402 client initialized for {self.address} on chain {chain_id}")

    def get_balance(self) -> float:
        """
        Get USDC balance.

        Returns:
            USDC balance in human-readable format
        """
        balance = self.usdc.functions.balanceOf(self.address).call()
        decimals = self.usdc.functions.decimals().call()
        return balance / (10 ** decimals)

    def process_payment(
        self,
        gateway_url: str,
        message: str,
        price_usdc: float
    ) -> Dict[str, Any]:
        """
        Process x402 payment through gateway using 402 challenge-response flow.

        Args:
            gateway_url: x402 gateway URL
            message: The message/query to send to the agent
            price_usdc: Price in USDC

        Returns:
            Agent response
        """
        logger.info(f"Processing x402 payment: ${price_usdc} USDC")

        # Check balance
        balance = self.get_balance()
        if balance < price_usdc:
            raise Exception(f"Insufficient USDC balance: {balance} < {price_usdc}")

        # Format request according to x402 spec
        request_body = {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": message}]
            }
        }

        try:
            # Step 1: Send initial request (will get Payment Required in metadata)
            logger.debug(f"Sending initial request to {gateway_url}")
            response = requests.post(
                gateway_url,
                json=request_body,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )

            # Step 2: Handle Payment Required (A2A style in message metadata)
            # Don't raise for 402 - it's expected in x402 protocol
            if response.status_code not in [200, 402]:
                response.raise_for_status()

            data = response.json()

            # Extract payment details from metadata
            payment_required = None
            task_id = None
            context_id = None

            if 'task' in data:
                task = data['task']
                task_id = task.get('id')
                context_id = task.get('contextId')

                if 'status' in task and 'message' in task['status']:
                    metadata = task['status']['message'].get('metadata', {})
                    payment_required = metadata.get('x402.payment.required')

            if payment_required and 'accepts' in payment_required:
                logger.debug("Payment required, processing EIP-3009 authorization...")

                # Get the payment option (first one)
                payment_option = payment_required['accepts'][0]

                logger.info(f"Payment required: {payment_option.get('maxAmountRequired')} on {payment_option.get('network')}")

                # Sign the payment using EIP-3009
                payment_payload = self._sign_payment_option(payment_option, message)

                # Step 3: Resubmit with payment in message metadata (A2A protocol)
                import time
                paid_message = {
                    "messageId": f"msg-{int(time.time() * 1000)}",
                    "role": "user",
                    "parts": [{"kind": "text", "text": message}],
                    "metadata": {
                        "x402.payment.payload": payment_payload,
                        "x402.payment.status": "payment-submitted"
                    }
                }

                paid_request = {
                    "message": paid_message
                }

                # Include task/context IDs if available
                if task_id:
                    paid_request["taskId"] = task_id
                if context_id:
                    paid_request["contextId"] = context_id

                logger.debug("Resubmitting with EIP-3009 payment authorization...")
                response = requests.post(
                    gateway_url,
                    json=paid_request,
                    headers={'Content-Type': 'application/json'},
                    timeout=60
                )

            # Allow 200 or 402 (both are valid in x402 protocol)
            if response.status_code not in [200, 402]:
                response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"x402 gateway request failed: {e}")
            raise Exception(f"x402 gateway request failed: {e}") from e
        except Exception as e:
            logger.error(f"x402 payment failed: {e}")
            raise Exception(f"Payment processing failed: {e}") from e

    def _sign_payment_option(self, payment_option: Dict[str, Any], message: str) -> Dict[str, Any]:
        """
        Sign payment using EIP-3009 transferWithAuthorization for x402 protocol.

        Args:
            payment_option: Payment option from accepts array
            message: Original message being paid for

        Returns:
            Payment object with EIP-3009 signature
        """
        from eth_account.messages import encode_typed_data
        import secrets
        import time

        # Generate nonce (32 random bytes)
        nonce = "0x" + secrets.token_hex(32)

        # Calculate validity period
        now = int(time.time())
        valid_after = 0
        valid_before = now + payment_option.get('maxTimeoutSeconds', 600)

        # Create EIP-3009 authorization
        authorization = {
            "from": self.address,
            "to": payment_option.get('payTo'),
            "value": str(payment_option.get('maxAmountRequired')),
            "validAfter": str(valid_after),
            "validBefore": str(valid_before),
            "nonce": nonce
        }

        # Create EIP-712 domain (USDC contract)
        domain = {
            "name": payment_option.get('extra', {}).get('name', 'USD Coin'),
            "version": payment_option.get('extra', {}).get('version', '2'),
            "chainId": self.chain_id,
            "verifyingContract": payment_option.get('asset')
        }

        # EIP-3009 TransferWithAuthorization types
        types = {
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"}
            ]
        }

        # Sign the typed data
        typed_data = encode_typed_data(
            domain_data=domain,
            message_types=types,
            message_data=authorization
        )

        signed = self.account.sign_message(typed_data)

        # Ensure signature has 0x prefix (compatible with ethers.js)
        signature = signed.signature.hex()
        if not signature.startswith("0x"):
            signature = "0x" + signature

        logger.debug(f"Created EIP-3009 authorization with nonce {nonce}")

        # Return x402 payment payload
        return {
            "x402Version": 1,
            "scheme": payment_option.get('scheme'),
            "network": payment_option.get('network'),
            "payload": {
                "signature": signature,
                "authorization": authorization
            }
        }
