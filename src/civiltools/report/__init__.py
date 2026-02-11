"""
Report subpackage — PDF and DOCX structural engineering reports.

Provides:
- ReportData:  dataclass holding all extracted ETABS data
- ReportConfig / ResultManifest: configuration helpers
- get_string / S: bilingual string catalogue
"""

from civiltools.report.report_config import ReportConfig, ResultManifest
from civiltools.report.strings import get_string, S
from civiltools.report.data_extractor import ReportData

__all__ = ["ReportConfig", "ResultManifest", "ReportData", "get_string", "S"]
