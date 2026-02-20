"""
Dashboard Data Access Layer - Package Init
Combines all data access mixins into a single DashboardData class.
"""
from dashboard.models.base import DashboardData as _BaseDashboardData
from dashboard.models.ar import ARDataMixin
from dashboard.models.attorneys import AttorneyDataMixin
from dashboard.models.tasks import TaskDataMixin
from dashboard.models.sop import SOPDataMixin
from dashboard.models.phases import PhasesDataMixin
from dashboard.models.trends import TrendsDataMixin


class DashboardData(
    _BaseDashboardData,
    ARDataMixin,
    AttorneyDataMixin,
    TaskDataMixin,
    SOPDataMixin,
    PhasesDataMixin,
    TrendsDataMixin,
):
    """
    Unified DashboardData class combining all domain-specific mixins.
    Provides read-only access to cached data from PostgreSQL database.
    """
    pass


__all__ = ['DashboardData']
