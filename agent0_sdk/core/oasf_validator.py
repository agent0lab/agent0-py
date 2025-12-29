"""
OASF taxonomy validation utilities.
"""

import json
import os
from pathlib import Path
from typing import Optional

# Cache for loaded taxonomy data
_skills_cache: Optional[dict] = None
_domains_cache: Optional[dict] = None


def _get_taxonomy_path(filename: str) -> Path:
    """Get the path to a taxonomy file."""
    # Get the directory where this file is located
    current_dir = Path(__file__).parent
    # Go up one level to agent0_sdk, then into taxonomies
    taxonomy_dir = current_dir.parent / "taxonomies"
    return taxonomy_dir / filename


def _load_skills() -> dict:
    """Load skills taxonomy file with caching."""
    global _skills_cache
    if _skills_cache is None:
        skills_path = _get_taxonomy_path("all_skills.json")
        try:
            with open(skills_path, "r", encoding="utf-8") as f:
                _skills_cache = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Skills taxonomy file not found: {skills_path}"
            )
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON in skills taxonomy file: {e}"
            )
    return _skills_cache


def _load_domains() -> dict:
    """Load domains taxonomy file with caching."""
    global _domains_cache
    if _domains_cache is None:
        domains_path = _get_taxonomy_path("all_domains.json")
        try:
            with open(domains_path, "r", encoding="utf-8") as f:
                _domains_cache = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Domains taxonomy file not found: {domains_path}"
            )
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON in domains taxonomy file: {e}"
            )
    return _domains_cache


def validate_skill(slug: str) -> bool:
    """
    Validate if a skill slug exists in the OASF taxonomy.
    
    Args:
        slug: The skill slug to validate (e.g., "natural_language_processing/natural_language_generation/summarization")
    
    Returns:
        True if the skill exists in the taxonomy, False otherwise
    
    Raises:
        FileNotFoundError: If the taxonomy file cannot be found
        ValueError: If the taxonomy file is invalid JSON
    """
    skills_data = _load_skills()
    skills = skills_data.get("skills", {})
    return slug in skills


def validate_domain(slug: str) -> bool:
    """
    Validate if a domain slug exists in the OASF taxonomy.
    
    Args:
        slug: The domain slug to validate (e.g., "finance_and_business/investment_services")
    
    Returns:
        True if the domain exists in the taxonomy, False otherwise
    
    Raises:
        FileNotFoundError: If the taxonomy file cannot be found
        ValueError: If the taxonomy file is invalid JSON
    """
    domains_data = _load_domains()
    domains = domains_data.get("domains", {})
    return slug in domains

