import logging
import asyncio
import time
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

class DockerManager:
    @staticmethod
    def is_docker_available() -> bool:
        try:
            import docker
            client = docker.from_env()
            client.ping()
            return True
        except Exception as e:
            logger.debug(f"Docker availability check failed: {e}")
            return False

    @staticmethod
    def sanitize_tag(name: str) -> str:
        # Docker image/container name format: lowercase, alphanumeric, -, _
        sanitized = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in name.lower())
        return sanitized.strip("-")

    @classmethod
    async def build_image(cls, path: str, tag_name: str) -> Tuple[bool, str]:
        if not cls.is_docker_available():
            return False, "❌ Docker Engine is unavailable on this host."

        def _build():
            import docker
            client = docker.from_env()
            try:
                # Build docker image
                image, build_logs = client.images.build(
                    path=path,
                    tag=tag_name,
                    rm=True,
                    forcerm=True
                )
                return True, "Build successful"
            except docker.errors.BuildError as e:
                log_lines = []
                for chunk in e.build_log:
                    if 'stream' in chunk:
                        log_lines.append(chunk['stream'])
                error_output = "".join(log_lines[-20:]) or str(e)
                return False, f"Docker build failed:\n{error_output}"
            except Exception as e:
                return False, f"Docker build error: {str(e)}"

        return await asyncio.to_thread(_build)

    @classmethod
    async def create_and_start_container(
        cls,
        image_name: str,
        container_name: str,
        env_vars: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Returns (success, message_or_error, container_id)
        """
        if not cls.is_docker_available():
            return False, "❌ Docker Engine is unavailable on this host.", None

        def _start():
            import docker
            client = docker.from_env()
            try:
                # Remove old container with same name if exists
                try:
                    old_c = client.containers.get(container_name)
                    old_c.stop(timeout=2)
                    old_c.remove(force=True)
                except docker.errors.NotFound:
                    pass
                except Exception:
                    pass

                container = client.containers.run(
                    image=image_name,
                    name=container_name,
                    detach=True,
                    restart_policy={"Name": "unless-stopped"},
                    environment=env_vars or {}
                )

                # Wait briefly to verify container stays running
                time.sleep(2)
                container.reload()

                if container.status in ("running", "created"):
                    return True, "Container started successfully", container.id
                else:
                    logs = container.logs(tail=30).decode('utf-8', errors='ignore')
                    return False, f"Container started but exited (status: {container.status}).\nLogs:\n{logs}", container.id
            except Exception as e:
                return False, f"Failed to start container: {str(e)}", None

        return await asyncio.to_thread(_start)

    @classmethod
    async def stop_container(cls, container_name: str) -> Tuple[bool, str]:
        if not cls.is_docker_available():
            return False, "❌ Docker Engine is unavailable on this host."

        def _stop():
            import docker
            client = docker.from_env()
            try:
                container = client.containers.get(container_name)
                container.stop(timeout=5)
                return True, "Container stopped successfully."
            except docker.errors.NotFound:
                return True, "Container already stopped or not found."
            except Exception as e:
                return False, f"Error stopping container: {str(e)}"

        return await asyncio.to_thread(_stop)

    @classmethod
    async def pause_container(cls, container_name: str) -> Tuple[bool, str]:
        if not cls.is_docker_available():
            return False, "❌ Docker Engine is unavailable on this host."

        def _pause():
            import docker
            client = docker.from_env()
            try:
                container = client.containers.get(container_name)
                container.stop(timeout=5)
                return True, "Container paused/stopped successfully."
            except docker.errors.NotFound:
                return True, "Container not found."
            except Exception as e:
                return False, f"Error pausing container: {str(e)}"

        return await asyncio.to_thread(_pause)

    @classmethod
    async def start_container(cls, container_name: str) -> Tuple[bool, str]:
        if not cls.is_docker_available():
            return False, "❌ Docker Engine is unavailable on this host."

        def _start():
            import docker
            client = docker.from_env()
            try:
                container = client.containers.get(container_name)
                container.start()
                time.sleep(2)
                container.reload()
                if container.status in ("running", "created"):
                    return True, "Container started successfully."
                else:
                    logs = container.logs(tail=30).decode('utf-8', errors='ignore')
                    return False, f"⚠️ Container started but exited.\n\nLogs:\n{logs}"
            except docker.errors.NotFound:
                return False, "Container not found."
            except Exception as e:
                return False, f"Error starting container: {str(e)}"

        return await asyncio.to_thread(_start)

    @classmethod
    async def restart_container(cls, container_name: str) -> Tuple[bool, str]:
        if not cls.is_docker_available():
            return False, "❌ Docker Engine is unavailable on this host."

        def _restart():
            import docker
            client = docker.from_env()
            try:
                container = client.containers.get(container_name)
                container.restart(timeout=5)
                time.sleep(2)
                container.reload()
                if container.status in ("running", "created"):
                    return True, "Container restarted successfully."
                else:
                    logs = container.logs(tail=30).decode('utf-8', errors='ignore')
                    return False, f"Container restarted but exited.\nLogs:\n{logs}"
            except docker.errors.NotFound:
                return False, "Container not found."
            except Exception as e:
                return False, f"Error restarting container: {str(e)}"

        return await asyncio.to_thread(_restart)

    @classmethod
    async def get_container_logs(cls, container_name: str, tail: int = 100) -> Tuple[bool, str]:
        if not cls.is_docker_available():
            return False, "❌ Docker Engine is unavailable on this host."

        def _logs():
            import docker
            client = docker.from_env()
            try:
                container = client.containers.get(container_name)
                logs_bytes = container.logs(tail=tail, timestamps=True)
                logs_str = logs_bytes.decode('utf-8', errors='ignore')
                return True, logs_str or "No logs available."
            except docker.errors.NotFound:
                return False, "Container not found."
            except Exception as e:
                return False, f"Error retrieving logs: {str(e)}"

        return await asyncio.to_thread(_logs)

    @classmethod
    async def remove_container_and_image(cls, container_name: str, image_name: Optional[str] = None) -> Tuple[bool, str]:
        if not cls.is_docker_available():
            return True, "Docker unavailable, skipping container cleanup."

        def _remove():
            import docker
            client = docker.from_env()
            messages = []
            try:
                container = client.containers.get(container_name)
                container.stop(timeout=3)
                container.remove(force=True)
                messages.append("Container removed.")
            except docker.errors.NotFound:
                messages.append("Container not found.")
            except Exception as e:
                messages.append(f"Container remove error: {e}")

            if image_name:
                try:
                    client.images.remove(image=image_name, force=True)
                    messages.append("Image removed.")
                except Exception as e:
                    messages.append(f"Image remove error: {e}")

            return True, " ".join(messages)

        return await asyncio.to_thread(_remove)

    @classmethod
    async def inspect_status(cls, container_name: str) -> str:
        if not cls.is_docker_available():
            return "UNKNOWN (DOCKER UNAVAILABLE)"

        def _inspect():
            import docker
            client = docker.from_env()
            try:
                container = client.containers.get(container_name)
                return container.status.upper()
            except docker.errors.NotFound:
                return "STOPPED"
            except Exception:
                return "UNKNOWN"

        return await asyncio.to_thread(_inspect)
