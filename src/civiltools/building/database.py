"""
Live Load Database Manager

Handles loading and querying the live load standards from JSON.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List

class LiveLoadDatabase:
    """
    Database manager for standard live loads.
    Loads data from JSON and provides query methods.
    """

    def __init__(self, data_file: Optional[Path] = None):
        """
        Initialize the database.
        
        Args:
            data_file: Path to the JSON data file. Defaults to live_load_data.json in the same directory.
        """
        if data_file is None:
            data_file = Path(__file__).parent / "live_load_data.json"

        self.data_file = data_file
        self._data: Dict[str, Any] = self._load_data()

    def _load_data(self) -> Dict[str, Any]:
        """Load the JSON file."""
        if not self.data_file.exists():
            raise FileNotFoundError(f"Live load data file not found: {self.data_file}")

        with open(self.data_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_load(self, use_type: str) -> float:
        """
        Get the default distributed live load for a specific use type.
        
        Args:
            use_type: The ID of the use type (e.g., 'office_general')
            
        Returns:
            The distributed load in kN/m²
            
        Raises:
            ValueError: If the use type is not found or has no default load.
        """
        if use_type not in self._data.get("uses", {}):
            raise ValueError(f"Unknown use type: {use_type}")
            
        load = self._data["uses"][use_type].get("default_load")
        if load is None:
            raise ValueError(f"Use type '{use_type}' has no default distributed load defined.")
            
        return float(load)

    def get_concentrated_load(self, use_type: str) -> Optional[float]:
        """Get the concentrated load for a use type, if applicable."""
        if use_type not in self._data.get("uses", {}):
            raise ValueError(f"Unknown use type: {use_type}")
        
        val = self._data["uses"][use_type].get("concentrated_load")
        return float(val) if val is not None else None

    def get_name(self, use_type: str) -> str:
        """Get the display name for a use type."""
        if use_type not in self._data.get("uses", {}):
            return use_type
        return self._data["uses"][use_type].get("name", use_type)

    def get_description(self, use_type: str) -> str:
        """Get the description for a use type."""
        if use_type not in self._data.get("uses", {}):
            return "Unknown"
        return self._data["uses"][use_type].get("description", "")

    def get_default_load(self) -> float:
        """Get the global default load for the project."""
        return float(self._data.get("default", {}).get("load", 2.0))

    def list_use_types(self) -> List[str]:
        """Get a list of all available use type IDs."""
        return list(self._data.get("uses", {}).keys())

    def list_use_types_with_names(self) -> Dict[str, str]:
        """Get a dictionary mapping use type IDs to their display names."""
        return {
            use_id: info.get("name", use_id)
            for use_id, info in self._data.get("uses", {}).items()
        }
