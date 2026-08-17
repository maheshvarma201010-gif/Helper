from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime

@dataclass
class UserConfig:
    user_id: int
    render_api_key: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class DeploymentRecord:
    user_id: int
    service_id: str
    service_name: str
    repo_url: str
    branch: str
    service_type: str  # web_service, background_worker, cron_job, static_site
    is_docker: bool
    status: str
    service_url: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class AuditLog:
    user_id: int
    action: str
    details: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
