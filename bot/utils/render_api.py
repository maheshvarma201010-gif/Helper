import aiohttp
import logging
from typing import Dict, Any, List, Optional
from bot.utils.formatter import sanitize_service_name

logger = logging.getLogger(__name__)

class RenderAPIError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"Render API Error ({status}): {message}")

class RenderAPI:
    BASE_URL = "https://api.render.com/v1"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    async def _request(self, method: str, endpoint: str, json_data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.BASE_URL}{endpoint}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.request(method, url, headers=self.headers, json=json_data, params=params, timeout=30) as resp:
                    if resp.status == 204:
                        return True
                    data = await resp.json() if resp.content_type == 'application/json' else await resp.text()
                    if resp.status >= 400:
                        if isinstance(data, dict):
                            err_msg = data.get("message") or data.get("error") or str(data)
                        elif isinstance(data, list):
                            err_msg = "; ".join([str(item) for item in data])
                        else:
                            err_msg = str(data)
                        logger.error(f"Render API HTTP {resp.status} for {endpoint}: {err_msg}")
                        raise RenderAPIError(resp.status, err_msg)
                    return data
            except aiohttp.ClientError as e:
                logger.error(f"Render API connection error: {e}")
                raise RenderAPIError(500, f"Network connection error: {str(e)}")

    async def get_owner_id(self) -> Optional[str]:
        try:
            owners = await self._request("GET", "/owners")
            if isinstance(owners, list) and len(owners) > 0:
                return owners[0].get("owner", {}).get("id") or owners[0].get("id")
        except Exception as e:
            logger.warning(f"Failed to fetch owner ID: {e}")
        return None

    async def list_services(self, limit: int = 20) -> List[Dict[str, Any]]:
        data = await self._request("GET", "/services", params={"limit": limit})
        if isinstance(data, list):
            return data
        return []

    async def get_service(self, service_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/services/{service_id}")

    async def update_service(self, service_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Updates a service (e.g. branch, repo, build details)."""
        return await self._request("PATCH", f"/services/{service_id}", json_data=updates)

    async def create_service(self, config: Dict[str, Any]) -> Dict[str, Any]:
        owner_id = config.get("ownerId")
        if not owner_id:
            owner_id = await self.get_owner_id()

        srv_type = config.get("type", "web_service")
        is_docker = config.get("is_docker", False) or (config.get("env") == "docker")
        env_vars_list = [{"key": k, "value": v} for k, v in config.get("env_vars", {}).items()]

        raw_plan = str(config.get("plan") or config.get("instance_type") or "free").lower().strip()
        if raw_plan in ["free", "0", "0/mo", "$0/mo", "select_plan_free", "zip_plan_free"]:
            plan_value = "free"
        elif raw_plan in ["starter", "7", "7/mo", "$7/mo", "select_plan_starter", "zip_plan_starter"]:
            plan_value = "starter"
        elif raw_plan in ["standard", "25", "$25/mo"]:
            plan_value = "standard"
        elif raw_plan in ["pro", "85", "$85/mo"]:
            plan_value = "pro"
        elif raw_plan in ["pro_plus", "175", "$175/mo"]:
            plan_value = "pro_plus"
        elif raw_plan in ["extra_pro", "225", "$225/mo"]:
            plan_value = "extra_pro"
        else:
            plan_value = raw_plan

        runtime_val = "docker" if is_docker else str(config.get("env", "python")).lower()

        if srv_type == "static_site":
            service_details: Dict[str, Any] = {
                "buildCommand": config.get("buildCommand", ""),
                "publishPath": config.get("publishPath", "public")
            }
        else:
            service_details = {
                "region": config.get("region", "oregon"),
                "plan": plan_value,
                "runtime": runtime_val,
                "env": runtime_val,
                "envVars": env_vars_list
            }

            if is_docker:
                docker_details = {
                    "dockerfilePath": config.get("dockerfilePath", "./Dockerfile"),
                    "dockerContext": config.get("dockerContext", ".")
                }
                if config.get("dockerCommand"):
                    docker_details["dockerCommand"] = config.get("dockerCommand")
                service_details["envSpecificDetails"] = docker_details
                service_details["dockerfilePath"] = config.get("dockerfilePath", "./Dockerfile")
                service_details["dockerContext"] = config.get("dockerContext", ".")
            else:
                native_details = {
                    "buildCommand": config.get("buildCommand", ""),
                    "startCommand": config.get("startCommand", "")
                }
                service_details["envSpecificDetails"] = native_details
                if config.get("buildCommand"):
                    service_details["buildCommand"] = config.get("buildCommand")
                if config.get("startCommand"):
                    service_details["startCommand"] = config.get("startCommand")

        raw_name = config.get("name") or config.get("repo_name") or "my-service"
        srv_name = sanitize_service_name(raw_name, fallback=config.get("repo_name") or "my-service")

        payload = {
            "type": srv_type,
            "name": srv_name,
            "ownerId": owner_id,
            "repo": config["repo"],
            "autoDeploy": config.get("autoDeploy", "yes"),
            "branch": config.get("branch", "main"),
            "serviceDetails": service_details
        }

        return await self._request("POST", "/services", json_data=payload)

    async def delete_service(self, service_id: str) -> bool:
        return await self._request("DELETE", f"/services/{service_id}")

    async def restart_service(self, service_id: str) -> bool:
        return await self._request("POST", f"/services/{service_id}/restart")

    async def suspend_service(self, service_id: str) -> bool:
        return await self._request("POST", f"/services/{service_id}/suspend")

    async def resume_service(self, service_id: str) -> bool:
        return await self._request("POST", f"/services/{service_id}/resume")

    async def redeploy_service(self, service_id: str, clear_cache: bool = False) -> Dict[str, Any]:
        params = {"clearCache": "clear"} if clear_cache else {}
        return await self._request("POST", f"/services/{service_id}/deploys", params=params)

    async def list_deploys(self, service_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        data = await self._request("GET", f"/services/{service_id}/deploys", params={"limit": limit})
        if isinstance(data, list):
            return [item.get("deploy", item) for item in data]
        return []

    async def get_deploy(self, service_id: str, deploy_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/services/{service_id}/deploys/{deploy_id}")

    async def get_env_vars(self, service_id: str) -> Dict[str, str]:
        data = await self._request("GET", f"/services/{service_id}/env-vars")
        result = {}
        if isinstance(data, list):
            for item in data:
                ev = item.get("envVar", item)
                result[ev["key"]] = ev["value"]
        return result

    async def update_env_vars(self, service_id: str, env_vars: Dict[str, str]) -> bool:
        payload = [{"key": k, "value": v} for k, v in env_vars.items()]
        await self._request("PUT", f"/services/{service_id}/env-vars", json_data=payload)
        return True
