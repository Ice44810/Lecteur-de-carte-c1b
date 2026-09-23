"""Couche de services : orchestration metier.

Sens des dependances, strictement respecte :

.. code-block:: text

    UI  ->  Service  ->  Repository  ->  Database
            |
            +->  Parser   (donnee brute -> donnee decodee)
            +->  Analysis (donnee metier -> analyse -> alerte)
            +->  Reports  (analyse -> rapport)

L'interface n'importe jamais ``app.database`` ni ``app.parser`` : elle ne connait que
les services et leurs objets de transfert.
"""

from app.services.analysis_service import AnalysisService, PeriodAnalysis, TimelineEntry
from app.services.base import BaseService
from app.services.dashboard_service import DashboardData, DashboardService
from app.services.driver_service import DriverNotFoundError, DriverService, DriverSummary
from app.services.import_service import FileInspection, ImportRecord, ImportService
from app.services.report_service import ReportFormat, ReportRequest, ReportService
from app.services.vehicle_service import VehicleNotFoundError, VehicleService, VehicleSummary

__all__ = [
    "AnalysisService",
    "BaseService",
    "DashboardData",
    "DashboardService",
    "DriverNotFoundError",
    "DriverService",
    "DriverSummary",
    "FileInspection",
    "ImportRecord",
    "ImportService",
    "PeriodAnalysis",
    "ReportFormat",
    "ReportRequest",
    "ReportService",
    "TimelineEntry",
    "VehicleNotFoundError",
    "VehicleService",
    "VehicleSummary",
]
