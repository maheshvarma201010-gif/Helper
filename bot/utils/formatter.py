import re
from typing import Dict, Any, Optional

def sanitize_service_name(name: str, fallback: str = "app-service") -> str:
    """
    Sanitizes service name for Render API requirements:
    - Lowercase
    - Alphanumeric characters and hyphens only
    - Max 63 characters
    - Non-empty
    """
    if not name or not isinstance(name, str):
        name = fallback or "app-service"

    cleaned = name.lower()
    cleaned = re.sub(r'[^a-z0-9-]+', '-', cleaned)
    cleaned = re.sub(r'-+', '-', cleaned).strip('-')

    if not cleaned:
        fallback_clean = re.sub(r'[^a-z0-9-]+', '-', (fallback or "app-service").lower()).strip('-')
        cleaned = fallback_clean or "app-service"

    return cleaned[:63].strip('-') or "app-service"

STATUS_BADGES = {
    "live": "🟢 RUNNING",
    "running": "🟢 RUNNING",
    "active": "🟢 RUNNING",
    "deploying": "🔄 DEPLOYING",
    "build_in_progress": "🟡 BUILDING",
    "building": "🟡 BUILDING",
    "created": "🟡 CREATED",
    "deactivated": "⚪ STOPPED",
    "suspended": "⚪ STOPPED",
    "stopped": "⚪ STOPPED",
    "build_failed": "🔴 FAILED",
    "update_failed": "🔴 FAILED",
    "failed": "🔴 FAILED",
    "canceled": "⚪ CANCELED"
}

def get_status_badge(status: str) -> str:
    return STATUS_BADGES.get(status.lower(), f"❓ {status.upper()}")

def format_service_card(service: Dict[str, Any], last_deploy: Optional[Dict[str, Any]] = None) -> str:
    srv_details = service.get("service", service)
    srv_id = srv_details.get("id", "N/A")
    name = srv_details.get("name", "Unknown")
    srv_type = srv_details.get("type", "web_service")
    repo = srv_details.get("repo", "N/A")
    auto_deploy = srv_details.get("autoDeploy", "yes")

    # Extract details from serviceDetails if available
    details = srv_details.get("serviceDetails", {})
    env = details.get("env", "N/A")
    region = details.get("region", srv_details.get("region", "oregon"))
    url = details.get("url", srv_details.get("url", ""))

    # Deployment info
    status_str = "created"
    if last_deploy:
        status_str = last_deploy.get("status", "created")
        commit = last_deploy.get("commit", {})
        commit_msg = commit.get("message", "N/A") if isinstance(commit, dict) else "N/A"
    else:
        commit_msg = "N/A"

    status_badge = get_status_badge(status_str)

    lines = [
        f"<b>{name}</b> ({srv_type})",
        f"<b>Status:</b> {status_badge}",
        f"<b>ID:</b> <code>{srv_id}</code>",
        f"<b>Region:</b> {region}",
        f"<b>Environment:</b> {env}",
        f"<b>Repository:</b> <code>{repo}</code>",
        f"<b>Auto Deploy:</b> {auto_deploy}"
    ]

    if url:
        lines.append(f"<b>URL:</b> {url}")

    if commit_msg != "N/A":
        lines.append(f"<b>Latest Commit:</b> {commit_msg[:50]}")

    return "\n".join(lines)

def format_deployment_preview(config: Dict[str, Any]) -> str:
    runtime = config.get("env", "docker" if config.get("is_docker") else "python")
    is_docker = (runtime == "docker") or config.get("is_docker", False)

    lines = [
        "🚀 <b>Deployment Preview</b>",
        "───────────────",
        f"<b>1. Service Name:</b> <code>{config.get('name')}</code>",
        f"<b>2. Repository:</b> <code>{config.get('repo')}</code>",
        f"<b>3. Language/Runtime:</b> {runtime}",
        f"<b>4. Branch:</b> <code>{config.get('branch', 'main')}</code>",
        f"<b>5. Region:</b> {config.get('region', 'oregon')}",
        f"<b>6. Compute Plan:</b> {config.get('plan', config.get('instance_type', 'free'))}",
        f"<b>7. Service Type:</b> {config.get('type', 'web_service')}"
    ]

    if is_docker:
        lines.append(f"<b>Dockerfile Path:</b> <code>{config.get('dockerfilePath', './Dockerfile')}</code>")
        lines.append(f"<b>Build Context:</b> <code>{config.get('dockerContext', '.')}</code>")
    else:
        lines.append(f"<b>Build Command:</b> <code>{config.get('buildCommand', 'N/A')}</code>")
        lines.append(f"<b>Start Command:</b> <code>{config.get('startCommand', 'N/A')}</code>")

    env_vars = config.get("env_vars", {})
    if env_vars:
        lines.append(f"<b>8. Environment Variables:</b> {len(env_vars)} configured")
    else:
        lines.append("<b>8. Environment Variables:</b> None")

    return "\n".join(lines)
