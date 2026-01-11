"""
IPFS client for decentralized storage with support for multiple providers:
- Local IPFS nodes
- Pinata IPFS pinning service
- Filecoin Pin service
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import os
import time
from typing import Any, Dict, Optional

try:
    import ipfshttpclient
except ImportError:
    ipfshttpclient = None

logger = logging.getLogger(__name__)


class IPFSClient:
    """Client for IPFS operations supporting multiple providers (local IPFS, Pinata, Filecoin Pin)."""

    def __init__(
        self, 
        url: Optional[str] = None, 
        filecoin_pin_enabled: bool = False, 
        filecoin_private_key: Optional[str] = None,
        pinata_enabled: bool = False,
        pinata_jwt: Optional[str] = None
    ):
        """Initialize IPFS client.
        
        Args:
            url: IPFS node URL (e.g., "http://localhost:5001")
            filecoin_pin_enabled: Enable Filecoin Pin integration
            filecoin_private_key: Private key for Filecoin Pin operations
            pinata_enabled: Enable Pinata integration
            pinata_jwt: JWT token for Pinata authentication
        """
        self.url = url
        self.filecoin_pin_enabled = filecoin_pin_enabled
        self.filecoin_private_key = filecoin_private_key
        self.pinata_enabled = pinata_enabled
        self.pinata_jwt = pinata_jwt
        self.client = None
        
        if pinata_enabled:
            self._verify_pinata_jwt()
        elif filecoin_pin_enabled:
            self._verify_filecoin_pin_installation()
        elif url and ipfshttpclient:
            self.client = ipfshttpclient.connect(url)
        elif url and not ipfshttpclient:
            raise ImportError(
                "IPFS dependencies not installed. Install with: pip install ipfshttpclient"
            )

    def _verify_pinata_jwt(self):
        """Verify Pinata JWT is provided."""
        if not self.pinata_jwt:
            raise ValueError("pinata_jwt is required when pinata_enabled=True")
        logger.debug("Pinata JWT configured")

    def _verify_filecoin_pin_installation(self):
        """Verify filecoin-pin CLI is installed."""
        try:
            result = subprocess.run(
                ['filecoin-pin', '--version'], 
                capture_output=True, 
                text=True, 
                check=True
            )
            logger.debug(f"Filecoin Pin CLI found: {result.stdout.strip()}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                "filecoin-pin CLI not found. "
                "Install it from: https://github.com/filecoin-project/filecoin-pin?tab=readme-ov-file#cli"
            )

    def _pin_to_filecoin(self, file_path: str) -> str:
        """Pin file to Filecoin using filecoin-pin CLI following the official guide."""
        # Check if environment file exists (as per guide)
        env_file = os.path.expanduser("~/.filecoin-pin-env")
        if not os.path.exists(env_file):
            raise RuntimeError(
                "Filecoin Pin environment file not found. Please run:\n"
                "  1. cast wallet new\n"
                "  2. Create ~/.filecoin-pin-env with PRIVATE_KEY and WALLET_ADDRESS\n"
                "  3. Get testnet tokens from https://faucet.calibnet.chainsafe-fil.io/\n"
                "  4. filecoin-pin payments setup --auto (one-time setup)"
            )
        
        # Load environment from file (as per guide)
        env = os.environ.copy()
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith('export '):
                        key, value = line[7:].strip().split('=', 1)
                        env[key] = value.strip('"\'')
        except Exception as e:
            raise RuntimeError(f"Error loading Filecoin Pin environment: {e}")
        
        if 'PRIVATE_KEY' not in env:
            raise RuntimeError("PRIVATE_KEY not found in environment file")
        
        try:
            import time
            cmd = ['filecoin-pin', 'add', '--bare', file_path]
            logger.debug(f"Running Filecoin CLI command: {' '.join(cmd)}")
            
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                env=env
            )
            elapsed_time = time.time() - start_time
            logger.debug(f"Filecoin CLI completed in {elapsed_time:.2f} seconds")
            
            # Parse the output to extract Root CID
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if 'Root CID:' in line:
                    return line.split('Root CID:')[1].strip()
            
            # Fallback: return the first line if parsing fails
            return lines[0] if lines else "unknown"
            
        except subprocess.CalledProcessError as e:
            # Handle specific error cases from the guide
            stderr_lower = e.stderr.lower()
            if "insufficient fil" in stderr_lower or "balance" in stderr_lower:
                raise RuntimeError(
                    f"Insufficient FIL for gas fees: {e.stderr}\n"
                    "Get test FIL from: https://faucet.calibnet.chainsafe-fil.io/\n"
                    "Then run: filecoin-pin payments setup --auto (one-time setup)"
                )
            elif "payment" in stderr_lower or "setup" in stderr_lower:
                raise RuntimeError(
                    f"Payment setup required: {e.stderr}\n"
                    "Run: filecoin-pin payments setup --auto (one-time setup)"
                )
            else:
                raise RuntimeError(f"Filecoin Pin 'add' command failed: {e.stderr}")

    def _pin_to_local_ipfs(self, data: str, **kwargs) -> str:
        """Pin data to local IPFS node."""
        if not self.client:
            raise RuntimeError("No IPFS client available")
        result = self.client.add_str(data, **kwargs)
        # add_str returns the CID directly as a string
        return result if isinstance(result, str) else result['Hash']

    def _pin_to_pinata(self, data: str, file_name: str = "file.json") -> str:
        """Pin data to Pinata using JWT authentication with v3 API."""
        import requests
        import tempfile
        import os
        
        # Pinata v3 API endpoint for uploading files
        url = "https://uploads.pinata.cloud/v3/files"
        
        # Pinata authentication using JWT
        headers = {
            "Authorization": f"Bearer {self.pinata_jwt}"
        }
        
        # Create a temporary file with the data
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(data)
            temp_path = f.name
        
        try:
            logger.debug("Pinning to Pinata v3 (public)")
            
            # Prepare the file for upload with public network setting
            with open(temp_path, 'rb') as file:
                files = {
                    'file': (file_name, file, 'application/json')
                }
                
                # Add network parameter to make file public
                data = {
                    'network': 'public'
                }
                
                response = requests.post(url, headers=headers, files=files, data=data)
            
            response.raise_for_status()
            result = response.json()
            
            # v3 API returns different structure - CID is nested in data
            cid = None
            if 'data' in result and 'cid' in result['data']:
                cid = result['data']['cid']
            elif 'cid' in result:
                cid = result['cid']
            elif 'IpfsHash' in result:
                cid = result['IpfsHash']
                
            if not cid:
                error_msg = f"No CID returned from Pinata. Response: {result}"
                logger.error(error_msg)
                raise ValueError(error_msg)
            logger.debug(f"Pinned to Pinata v3: {cid}")
            return cid
        except requests.exceptions.HTTPError as e:
            error_details = ""
            if hasattr(e, 'response') and e.response is not None:
                error_details = f" Response: {e.response.text}"
            error_msg = f"Failed to pin to Pinata: HTTP {e}{error_details}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"Failed to pin to Pinata: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_path)
            except:
                pass

    def add(self, data: str, **kwargs) -> str:
        """Add data to IPFS and return CID."""
        file_name = kwargs.pop("file_name", None)
        if self.pinata_enabled:
            return self._pin_to_pinata(data, file_name=file_name or "file.json")
        elif self.filecoin_pin_enabled:
            # Create temporary file for Filecoin Pin
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(data)
                temp_path = f.name
            
            try:
                cid = self._pin_to_filecoin(temp_path)
                return cid
            finally:
                os.unlink(temp_path)
        else:
            return self._pin_to_local_ipfs(data, **kwargs)

    def add_file(self, filepath: str, **kwargs) -> str:
        """Add file to IPFS and return CID."""
        file_name = kwargs.pop("file_name", None)
        if self.pinata_enabled:
            # Read file and send to Pinata
            with open(filepath, 'r') as f:
                data = f.read()
            return self._pin_to_pinata(data, file_name=file_name or "file.json")
        elif self.filecoin_pin_enabled:
            return self._pin_to_filecoin(filepath)
        else:
            if not self.client:
                raise RuntimeError("No IPFS client available")
            result = self.client.add(filepath, **kwargs)
            return result['Hash']

    def get(self, cid: str) -> str:
        """Get data from IPFS by CID."""
        # Extract CID from IPFS URL if needed
        if cid.startswith("ipfs://"):
            cid = cid[7:]  # Remove "ipfs://" prefix
        
        # Pinata and Filecoin Pin both use IPFS gateways for retrieval
        if self.pinata_enabled or self.filecoin_pin_enabled:
            # Use IPFS gateways for retrieval
            import requests
            try:
                # Try multiple gateways for reliability, prioritizing Pinata v3 gateway
                gateways = [
                    f"https://gateway.pinata.cloud/ipfs/{cid}",
                    f"https://ipfs.io/ipfs/{cid}",
                    f"https://dweb.link/ipfs/{cid}"
                ]
                
                for gateway in gateways:
                    try:
                        response = requests.get(gateway, timeout=10)
                        response.raise_for_status()
                        return response.text
                    except Exception:
                        continue
                
                raise RuntimeError(f"Failed to retrieve data from all IPFS gateways")
            except Exception as e:
                raise RuntimeError(f"Failed to retrieve data from IPFS gateway: {e}")
        else:
            if not self.client:
                raise RuntimeError("No IPFS client available")
            return self.client.cat(cid).decode('utf-8')

    def get_json(self, cid: str) -> Dict[str, Any]:
        """Get JSON data from IPFS by CID."""
        data = self.get(cid)
        return json.loads(data)

    def pin(self, cid: str) -> Dict[str, Any]:
        """Pin a CID to local node."""
        if self.filecoin_pin_enabled:
            # Filecoin Pin automatically pins data, so this is a no-op
            return {"pinned": [cid]}
        else:
            if not self.client:
                raise RuntimeError("No IPFS client available")
            return self.client.pin.add(cid)

    def unpin(self, cid: str) -> Dict[str, Any]:
        """Unpin a CID from local node."""
        if self.filecoin_pin_enabled:
            # Filecoin Pin doesn't support unpinning in the same way
            # This is a no-op for Filecoin Pin
            return {"unpinned": [cid]}
        else:
            if not self.client:
                raise RuntimeError("No IPFS client available")
            return self.client.pin.rm(cid)

    def add_json(self, data: Dict[str, Any], **kwargs) -> str:
        """Add JSON data to IPFS and return CID."""
        json_str = json.dumps(data, indent=2)
        return self.add(json_str, **kwargs)

    def addRegistrationFile(self, registrationFile: "RegistrationFile", chainId: Optional[int] = None, identityRegistryAddress: Optional[str] = None, **kwargs) -> str:
        """Add registration file to IPFS and return CID."""
        data = registrationFile.to_dict(chain_id=chainId, identity_registry_address=identityRegistryAddress)
        return self.add_json(data, file_name="agent-registration.json", **kwargs)

    def getRegistrationFile(self, cid: str) -> "RegistrationFile":
        """Get registration file from IPFS by CID."""
        from .models import RegistrationFile
        data = self.get_json(cid)
        return RegistrationFile.from_dict(data)

    def addFeedbackFile(self, feedbackData: Dict[str, Any], **kwargs) -> str:
        """Add feedback file to IPFS and return CID."""
        return self.add_json(feedbackData, file_name="feedback.json", **kwargs)

    def getFeedbackFile(self, cid: str) -> Dict[str, Any]:
        """Get feedback file from IPFS by CID."""
        return self.get_json(cid)

    def close(self):
        """Close IPFS client connection."""
        if hasattr(self.client, 'close'):
            self.client.close()

