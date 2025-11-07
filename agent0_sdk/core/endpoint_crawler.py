"""
Endpoint Crawler for MCP and A2A Servers
Automatically fetches capabilities (tools, prompts, resources, skills) from endpoints
when an agent is registered. Uses soft failure - never blocks registration.
"""

import logging
import requests
import json
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# JSON-RPC helpers
def create_jsonrpc_request(method: str, params: Dict = None, request_id: int = 1):
    """Create a JSON-RPC request."""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "id": request_id
    }
    if params:
        payload["params"] = params
    return payload


class EndpointCrawler:
    """Crawls MCP and A2A endpoints to fetch capabilities."""
    
    def __init__(self, timeout: int = 5):
        """
        Initialize the endpoint crawler.
        
        Args:
            timeout: Request timeout in seconds (default: 5)
        """
        self.timeout = timeout
    
    def fetch_mcp_capabilities(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """
        Fetch MCP capabilities (tools, prompts, resources) from an MCP server.
        
        MCP Protocol uses JSON-RPC over HTTP POST. Tries JSON-RPC first,
        then falls back to static agentcard.json.
        
        Args:
            endpoint: MCP endpoint URL (must be http:// or https://)
            
        Returns:
            Dict with keys: 'mcpTools', 'mcpPrompts', 'mcpResources'
            Returns None if unable to fetch
        """
        # Ensure endpoint is HTTP/HTTPS
        if not endpoint.startswith(('http://', 'https://')):
            logger.warning(f"MCP endpoint must be HTTP/HTTPS, got: {endpoint}")
            return None
        
        # Try JSON-RPC approach first (for real MCP servers)
        capabilities = self._fetch_via_jsonrpc(endpoint)
        if capabilities:
            return capabilities
        
        # Fallback to static agentcard.json
        try:
            agentcard_url = f"{endpoint}/agentcard.json"
            logger.debug(f"Attempting to fetch MCP capabilities from {agentcard_url}")
            
            response = requests.get(agentcard_url, timeout=self.timeout, allow_redirects=True)
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract capabilities from agentcard
                capabilities = {
                    'mcpTools': self._extract_list(data, 'tools'),
                    'mcpPrompts': self._extract_list(data, 'prompts'),
                    'mcpResources': self._extract_list(data, 'resources')
                }
                
                if any(capabilities.values()):
                    logger.info(f"Successfully fetched MCP capabilities from {endpoint}")
                    return capabilities
                    
        except Exception as e:
            logger.debug(f"Could not fetch MCP capabilities from {endpoint}: {e}")
        
        return None
    
    def _fetch_via_jsonrpc(self, http_url: str) -> Optional[Dict[str, Any]]:
        """Try to fetch capabilities via JSON-RPC."""
        try:
            # Try to call list_tools, list_resources, list_prompts
            tools = self._jsonrpc_call(http_url, "tools/list")
            resources = self._jsonrpc_call(http_url, "resources/list")
            prompts = self._jsonrpc_call(http_url, "prompts/list")
            
            mcp_tools = []
            mcp_resources = []
            mcp_prompts = []
            
            # Extract names from tools
            if tools and isinstance(tools, dict) and "tools" in tools:
                for tool in tools["tools"]:
                    if isinstance(tool, dict) and "name" in tool:
                        mcp_tools.append(tool["name"])
            
            # Extract names from resources
            if resources and isinstance(resources, dict) and "resources" in resources:
                for resource in resources["resources"]:
                    if isinstance(resource, dict) and "name" in resource:
                        mcp_resources.append(resource["name"])
            
            # Extract names from prompts
            if prompts and isinstance(prompts, dict) and "prompts" in prompts:
                for prompt in prompts["prompts"]:
                    if isinstance(prompt, dict) and "name" in prompt:
                        mcp_prompts.append(prompt["name"])
            
            if mcp_tools or mcp_resources or mcp_prompts:
                logger.info(f"Successfully fetched MCP capabilities via JSON-RPC")
                return {
                    'mcpTools': mcp_tools,
                    'mcpResources': mcp_resources,
                    'mcpPrompts': mcp_prompts
                }
        
        except Exception as e:
            logger.debug(f"JSON-RPC approach failed: {e}")
        
        return None
    
    def _jsonrpc_call(self, url: str, method: str, params: Dict = None) -> Optional[Dict[str, Any]]:
        """Make a JSON-RPC call and return the result. Handles SSE format."""
        try:
            payload = create_jsonrpc_request(method, params or {})
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream'
            }
            response = requests.post(url, json=payload, timeout=self.timeout, headers=headers, stream=True)
            
            if response.status_code == 200:
                # Check if response is SSE format
                content_type = response.headers.get('content-type', '')
                if 'text/event-stream' in content_type or 'event: message' in response.text[:200]:
                    # Parse SSE format
                    result = self._parse_sse_response(response.text)
                    if result:
                        return result
                else:
                    # Regular JSON response
                    result = response.json()
                    if "result" in result:
                        return result["result"]
                    return result
        except Exception as e:
            logger.debug(f"JSON-RPC call {method} failed: {e}")
        
        return None
    
    def _parse_sse_response(self, sse_text: str) -> Optional[Dict[str, Any]]:
        """Parse Server-Sent Events (SSE) format response."""
        try:
            # Look for "data:" lines containing JSON
            for line in sse_text.split('\n'):
                if line.startswith('data: '):
                    json_str = line[6:]  # Remove "data: " prefix
                    data = json.loads(json_str)
                    if "result" in data:
                        return data["result"]
                    return data
        except Exception as e:
            logger.debug(f"Failed to parse SSE response: {e}")
        
        return None
    
    def fetch_a2a_capabilities(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """
        Fetch A2A capabilities (skills) from an A2A server.

        A2A Protocol uses agent cards to describe agent capabilities.
        Tries multiple well-known paths: agentcard.json, .well-known/agent.json, .well-known/agent-card.json

        Args:
            endpoint: A2A endpoint URL (must be http:// or https://)

        Returns:
            Dict with key: 'a2aSkills'
            Returns None if unable to fetch
        """
        try:
            # Ensure endpoint is HTTP/HTTPS
            if not endpoint.startswith(('http://', 'https://')):
                logger.warning(f"A2A endpoint must be HTTP/HTTPS, got: {endpoint}")
                return None

            # Try multiple well-known paths for A2A agent cards
            # Per ERC-8004, endpoint may already be full URL to agent card
            # Per A2A spec section 5.3, recommended discovery path is /.well-known/agent-card.json
            agentcard_urls = [
                endpoint,  # Try exact URL first (ERC-8004 format: full path to agent card)
                f"{endpoint}/.well-known/agent-card.json",  # Spec-recommended discovery path
                f"{endpoint.rstrip('/')}/.well-known/agent-card.json",
                f"{endpoint}/.well-known/agent.json",  # Alternative well-known path
                f"{endpoint.rstrip('/')}/.well-known/agent.json",
                f"{endpoint}/agentcard.json"  # Legacy path
            ]

            for agentcard_url in agentcard_urls:
                logger.debug(f"Attempting to fetch A2A capabilities from {agentcard_url}")

                try:
                    response = requests.get(agentcard_url, timeout=self.timeout, allow_redirects=True)

                    if response.status_code == 200:
                        data = response.json()

                        # Extract skill tags from agentcard
                        skills = self._extract_a2a_skills(data)

                        if skills:
                            logger.info(f"Successfully fetched A2A capabilities from {agentcard_url}: {len(skills)} skills")
                            return {'a2aSkills': skills}
                except requests.exceptions.RequestException as e:
                    # Try next URL
                    logger.debug(f"Failed to fetch from {agentcard_url}: {e}")
                    continue

        except Exception as e:
            logger.debug(f"Unexpected error fetching A2A capabilities from {endpoint}: {e}")

        return None

    def _extract_a2a_skills(self, data: Dict[str, Any]) -> List[str]:
        """
        Extract skill tags from A2A agent card.

        Per A2A Protocol spec (v0.3.0), agent cards should have:
          skills: AgentSkill[] where each AgentSkill has a tags[] array

        This method also handles non-standard formats for backward compatibility:
        - detailedSkills[].tags[] (custom extension)
        - skills: ["tag1", "tag2"] (non-compliant flat array)

        Args:
            data: Agent card JSON data

        Returns:
            List of unique skill tags (strings)
        """
        result = []

        # Try spec-compliant format first: skills[].tags[]
        if 'skills' in data and isinstance(data['skills'], list):
            for skill in data['skills']:
                if isinstance(skill, dict) and 'tags' in skill:
                    # Spec-compliant: AgentSkill object with tags
                    tags = skill['tags']
                    if isinstance(tags, list):
                        for tag in tags:
                            if isinstance(tag, str):
                                result.append(tag)
                elif isinstance(skill, str):
                    # Non-compliant: flat string array (fallback)
                    result.append(skill)

        # Fallback to detailedSkills if no tags found in skills
        # (custom extension used by some implementations)
        if not result and 'detailedSkills' in data and isinstance(data['detailedSkills'], list):
            for skill in data['detailedSkills']:
                if isinstance(skill, dict) and 'tags' in skill:
                    tags = skill['tags']
                    if isinstance(tags, list):
                        for tag in tags:
                            if isinstance(tag, str):
                                result.append(tag)

        # Remove duplicates while preserving order
        seen = set()
        unique_result = []
        for item in result:
            if item not in seen:
                seen.add(item)
                unique_result.append(item)

        return unique_result
    
    def _extract_list(self, data: Dict[str, Any], key: str) -> List[str]:
        """
        Extract a list of strings from nested JSON data.
        
        Args:
            data: JSON data dictionary
            key: Key to extract (e.g., 'tools', 'prompts', 'resources', 'skills')
            
        Returns:
            List of string names/IDs
        """
        result = []
        
        # Try top-level key
        if key in data and isinstance(data[key], list):
            for item in data[key]:
                if isinstance(item, str):
                    result.append(item)
                elif isinstance(item, dict):
                    # For objects, try to extract name/id field
                    for name_field in ['name', 'id', 'identifier', 'title']:
                        if name_field in item and isinstance(item[name_field], str):
                            result.append(item[name_field])
                            break
        
        # Try nested in 'capabilities' or 'abilities'
        if not result:
            for container_key in ['capabilities', 'abilities', 'features']:
                if container_key in data and isinstance(data[container_key], dict):
                    if key in data[container_key] and isinstance(data[container_key][key], list):
                        for item in data[container_key][key]:
                            if isinstance(item, str):
                                result.append(item)
                            elif isinstance(item, dict):
                                for name_field in ['name', 'id', 'identifier', 'title']:
                                    if name_field in item and isinstance(item[name_field], str):
                                        result.append(item[name_field])
                                        break
                    if result:
                        break
        
        return result
