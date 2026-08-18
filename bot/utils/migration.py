import logging
from typing import Dict, Any, List, Optional
from bot.utils.render_api import RenderAPI, RenderAPIError
from bot.utils.formatter import sanitize_service_name
from bot.database.mongo import db

logger = logging.getLogger(__name__)

def update_env_base_urls(env_vars: Dict[str, str], old_url: str = "", new_url: str = "") -> Dict[str, str]:
    """
    Automatically updates BASE_URL, CDN_URL, WEBSITE_URL, or any matching URL references
    in environment variables to the new service URL.
    """
    updated = dict(env_vars) if env_vars else {}

    if not new_url:
        return updated

    clean_old_url = old_url.rstrip("/") if old_url else ""
    clean_new_url = new_url.rstrip("/")

    # Update explicit BASE_URL if present or missing
    if "BASE_URL" in updated or not updated:
        updated["BASE_URL"] = clean_new_url

    # Replaces old_url occurrences across all env vars
    for k, v in list(updated.items()):
        if not isinstance(v, str):
            continue

        if k.upper() in ["BASE_URL", "WEBSITE_URL", "CDN_URL", "APP_URL", "URL"]:
            updated[k] = clean_new_url
        elif clean_old_url and clean_old_url in v:
            updated[k] = v.replace(clean_old_url, clean_new_url)

    return updated

async def execute_account_migration(old_api_key: str, new_api_key: str, user_id: int, selected_services: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Executes service migration from old Render account to new Render account:
    1. Creates all selected services on the NEW Render account using new_api_key.
    2. Automatically updates BASE_URL environment variables to point to the new service URL.
    3. AFTER all selected services are created on the new account, suspends all old services on the old account using old_api_key.
    4. Saves new_api_key to MongoDB.
    """
    old_render = RenderAPI(old_api_key)
    new_render = RenderAPI(new_api_key)

    deployed_results = []
    failed_services = []

    # Step 1: Deploy all selected services to the NEW account
    for item in selected_services:
        srv_details = item.get("service", item)
        old_srv_id = srv_details.get("id")
        srv_name = srv_details.get("name", "app-service")
        repo_url = srv_details.get("repo")
        srv_type = srv_details.get("type", "web_service")
        details = srv_details.get("serviceDetails", {})
        branch = srv_details.get("branch") or details.get("branch") or "main"
        env_type = details.get("env", "python")
        is_docker = (env_type == "docker")
        old_url = details.get("url", srv_details.get("url", ""))

        # Fetch old env vars if not present
        try:
            old_env_vars = await old_render.get_env_vars(old_srv_id)
        except Exception as e:
            logger.warning(f"Could not fetch env vars for old service {old_srv_id}: {e}")
            old_env_vars = {}

        deploy_config = {
            "name": sanitize_service_name(srv_name),
            "repo": repo_url,
            "branch": branch,
            "type": srv_type,
            "is_docker": is_docker,
            "dockerfilePath": details.get("dockerfilePath", "./Dockerfile"),
            "dockerContext": details.get("dockerContext", "."),
            "buildCommand": details.get("buildCommand", ""),
            "startCommand": details.get("startCommand", ""),
            "instance_type": details.get("plan", "free"),
            "env_vars": old_env_vars
        }

        try:
            res = await new_render.create_service(deploy_config)
            srv = res.get("service", res)
            new_srv_id = srv.get("id")
            new_srv_name = srv.get("name")
            new_url = srv.get("serviceDetails", {}).get("url", "")

            # Update BASE_URL and domain env vars on new service
            if new_url and old_env_vars:
                updated_env_vars = update_env_base_urls(old_env_vars, old_url, new_url)
                try:
                    await new_render.update_env_vars(new_srv_id, updated_env_vars)
                except Exception as e_env:
                    logger.warning(f"Failed to update env vars for new service {new_srv_id}: {e_env}")

            await db.save_deployment(
                user_id=user_id,
                service_id=new_srv_id,
                service_name=new_srv_name,
                repo_url=repo_url,
                branch=branch,
                service_type=srv_type,
                is_docker=is_docker,
                status="created",
                service_url=new_url
            )

            deployed_results.append({
                "old_id": old_srv_id,
                "new_id": new_srv_id,
                "name": new_srv_name,
                "url": new_url or f"https://{new_srv_name}.onrender.com"
            })
        except Exception as e:
            logger.error(f"Failed to deploy service {srv_name} to new Render account: {e}")
            failed_services.append({"id": old_srv_id, "name": srv_name, "error": str(e)})

    # Step 2: ONLY AFTER all selected services are deployed on NEW account, suspend old services on OLD account
    suspended_results = []
    for res in deployed_results:
        old_id = res["old_id"]
        try:
            await old_render.suspend_service(old_id)
            suspended_results.append(old_id)
            logger.info(f"Suspended old service {old_id} on old Render account")
        except Exception as e:
            logger.warning(f"Failed to suspend old service {old_id} on old Render account: {e}")

    # Step 3: Save new_api_key in MongoDB
    await db.set_user_render_key(user_id, new_api_key)

    return {
        "success": len(deployed_results) > 0,
        "deployed": deployed_results,
        "failed": failed_services,
        "suspended_count": len(suspended_results)
    }
