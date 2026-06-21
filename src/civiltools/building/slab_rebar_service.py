"""Slab Rebar Service — read from ETABS, cache, and prepare for export."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)


class SlabRebarService:
    """Isolate ETABS I/O and data transformation for slab rebar operations."""

    def __init__(self, etabs: Any):
        """Initialize service with ETABS connection."""
        self.etabs = etabs
        self._cache: pd.DataFrame | None = None

    def read_slab_rebars(
        self,
        stories: list[str] | None = None,
        strip_objects: list[str] | None = None,
        layers: list[str] | None = None,
        top_bottom: str = "both",
    ) -> pd.DataFrame:
        """Read slab rebar data from ETABS database.
        
        Args:
            stories: Filter by story names, or None for all
            strip_objects: Filter by strip object names, or None for all
            layers: Filter by layer names (A, B, Other), or None for all
            top_bottom: "top", "bot", or "both"
        
        Returns:
            DataFrame with slab rebar data; may contain columns like:
            Story, StripObject, Layer, TopBot, Station, Region, Area, etc.
        """
        try:
            # Call etabs_api database function
            df = self.etabs.database.get_slab_rebars_for_drawing(
                stories=stories,
                strip_objects=strip_objects,
                layers=layers,
                top_bottom=top_bottom,
                statuses=None,
            )
            
            if df is None or df.empty:
                raise ValueError(
                    "No slab rebar data found in ETABS. "
                    "Ensure: 1) slab design has been run, "
                    "2) Design Results table exists and is populated, "
                    "3) Filters are correct."
                )
            
            log.info(f"Read {len(df)} slab rebar rows from ETABS")
            self._cache = df.copy()
            return df
        
        except AttributeError as e:
            raise RuntimeError(
                f"ETABS database method 'get_slab_rebars_for_drawing' not available: {e}. "
                "Ensure etabs_api is installed and up-to-date."
            )
        except Exception as e:
            raise RuntimeError(f"Failed to read slab rebars: {e}")

    def get_cached_data(self) -> pd.DataFrame | None:
        """Return the cached dataframe, or None if not yet read."""
        return self._cache.copy() if self._cache is not None else None

    def clear_cache(self):
        """Clear the cache."""
        self._cache = None

    def transform_to_groups(
        self,
        data: pd.DataFrame,
        separate_layers: bool = False,
    ) -> list[dict[str, Any]]:
        """Transform raw data into grouped plans.
        
        When separate_layers=True, group by (Story, Layer, TopBot).
        When separate_layers=False, group by (Story, TopBot) (merge layers).
        
        Args:
            data: Raw slab rebar dataframe
            separate_layers: If True, one group per layer; if False, merge layers
        
        Returns:
            List of dicts with keys:
              - key: str (group identifier)
              - data: DataFrame (rows for this group)
              - story: str
              - layer: str or "All"
              - side: "top" or "bottom"
        """
        if data is None or data.empty:
            return []
        
        if separate_layers:
            # Group by (Story, Layer, TopBot)
            key_cols = ["Story", "Layer", "TopBot"]
        else:
            # Group by (Story, TopBot), merge all layers
            key_cols = ["Story", "TopBot"]
            data = data.copy()
            data["Layer"] = "All"  # Override to merge
        
        groups = []
        for group_key, group_df in data.groupby(key_cols):
            # Unpack tuple key
            if separate_layers:
                story, layer, side = group_key
            else:
                story, side = group_key
                layer = "All"
            
            key_str = f"{story}_{layer}_{side}".replace(" ", "_").lower()
            groups.append({
                "key": key_str,
                "data": group_df.reset_index(drop=True),
                "story": story,
                "layer": layer,
                "side": side,
            })
        
        log.info(f"Transformed into {len(groups)} export groups")
        return groups

    def get_optimizer_params(self) -> dict[str, float]:
        """Return default optimizer parameters."""
        return {
            "continuous_rebar_top": 150,
            "continuous_rebar_bot": 300,
            "region_threshold": 0.0,
            "min_area_threshold": 0.0,
            "extend_length": 0.0,
            "min_bar_length": 0.0,
        }
