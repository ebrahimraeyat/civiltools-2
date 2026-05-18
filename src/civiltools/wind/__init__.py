"""
civiltools.wind
===============
Wind load calculation modules for free-standing billboards and structures
according to Iranian National Building Code – Section 6 (مبحث ششم), Chapter 10.
"""

from civiltools.wind.billboard import (
    BillboardInputs,
    WindLoadOutput,
    calculate_wind_load,
)

__all__ = ["BillboardInputs", "WindLoadOutput", "calculate_wind_load"]
