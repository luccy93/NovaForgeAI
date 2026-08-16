"""Site Reliability Engineering (Volume 35).

Production reliability platform: service catalog, SLOs, error budgets,
incident management, disaster recovery, chaos engineering, capacity
planning, and automated operations for NovaForge AI.

Importing this package registers the SRE SQLAlchemy models on the global
Base metadata so that schema creation (tests) and Alembic autogenerate
see every table.
"""

from app.sre import models as _models  # noqa: F401
from app.sre import constants as _constants  # noqa: F401
