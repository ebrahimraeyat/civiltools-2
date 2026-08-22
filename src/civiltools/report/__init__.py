"""
Report subpackage — DOCX structural engineering reports.

Provides:
- ReportData:  dataclass holding all extracted ETABS data
- ReportConfig / ResultManifest: configuration helpers
- get_string / S: bilingual string catalogue
"""

from civiltools.report.data_extractor import ReportData
from civiltools.report.report_config import ReportConfig, ResultManifest
from civiltools.report.report_generator import ReportGenerator
from civiltools.report.strings import S, get_string

__all__ = [
    "ReportConfig",
    "ResultManifest",
    "ReportData",
    "ReportGenerator",
    "get_string",
    "S",
]
