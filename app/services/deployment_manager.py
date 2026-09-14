import os
import shutil
import logging
import asyncio
from typing import Optional, Tuple, Dict, Any, Set
from app.database import Database
from app.services.zip_manager import ZipManager, ZipValidationError
from app.services.docker_manager import DockerManager

logger = logging.getLogger(__name__)

# Mutex set to track active deployments by project ID
_ACTIVE_DEPLOYMENTS: Set[str] = set()
_DEPLOYMENT_LOCK = asyncio.Lock()

class DeploymentManager:
    @staticmethod
    async def is_project_deploying(project_id: str) -> bool:
        async with _DEPLOYMENT_LOCK:
            return project_id in _ACTIVE_DEPLOYMENTS

    @classmethod
    async def deploy_new_project(
        cls,
        zip_file_path: str,
        zip_filename: str,
        admin_id: int,
        status_callback=None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Deploys a new project from a ZIP file.
        status_callback(msg: str) can be an async function to update user on progress.
        """
        async def report(msg: str):
            if status_callback:
                try:
                    await status_callback(msg)
                except Exception:
                    pass

        if not DockerManager.is_docker_available():
            return False, "❌ Docker Engine is unavailable on this host.", None

        project_id = ZipManager.generate_project_id()
        raw_name = ZipManager.sanitize_project_name(zip_filename)
        project_name = raw_name
        image_name = DockerManager.sanitize_tag(f"telegram-project-{project_id}")
        container_name = DockerManager.sanitize_tag(f"telegram-project-{project_id}")

        async with _DEPLOYMENT_LOCK:
            _ACTIVE_DEPLOYMENTS.add(project_id)

        deployments_base = os.path.abspath("deployments")
        os.makedirs(deployments_base, exist_ok=True)
        extract_dir = os.path.join(deployments_base, project_id)

        try:
            await report("📦 ZIP received\n↓\n📥 Downloading")
            await report("📥 Downloading\n↓\n📂 Extracting")

            try:
                ZipManager.validate_and_extract_zip(zip_file_path, extract_dir)
            except ZipValidationError as ve:
                return False, f"❌ ZIP Validation Error: {str(ve)}", None

            await report("📂 Extracting\n↓\n🔍 Finding Dockerfile")
            context_dir, error = ZipManager.find_dockerfile_context(extract_dir)
            if error:
                return False, error, None

            await report("✅ Dockerfile found\n↓\n🔨 Building Docker image")
            build_success, build_msg = await DockerManager.build_image(context_dir, image_name)
            if not build_success:
                return False, f"❌ Docker Build Failed:\n{build_msg}", None

            await report("🔨 Building Docker image\n↓\n🚀 Creating container")
            await report("🚀 Creating container\n↓\n▶️ Starting container")

            start_success, start_msg, container_id = await DockerManager.create_and_start_container(
                image_name=image_name,
                container_name=container_name,
                env_vars={}
            )

            await report("▶️ Starting container\n↓\n🔎 Checking status")

            if not start_success:
                return False, f"❌ Container Startup Failed:\n{start_msg}", None

            project_doc = {
                "project_id": project_id,
                "project_name": project_name,
                "admin_id": admin_id,
                "zip_filename": zip_filename,
                "image_name": image_name,
                "container_name": container_name,
                "status": "RUNNING",
                "deployment_path": extract_dir,
                "last_error": None,
                "env_vars": {}
            }

            await Database.create_project(project_doc)
            await report("🔎 Checking status\n↓\n✅ Running")

            return True, "✅ Deployment successful", project_doc

        except Exception as e:
            logger.exception("Unexpected error during deployment")
            return False, f"❌ Unexpected deployment error: {str(e)}", None
        finally:
            async with _DEPLOYMENT_LOCK:
                _ACTIVE_DEPLOYMENTS.discard(project_id)

    @classmethod
    async def replace_project_zip(
        cls,
        project_id: str,
        zip_file_path: str,
        zip_filename: str,
        status_callback=None
    ) -> Tuple[bool, str]:
        """
        Safe zero-downtime replacement strategy:
        Build new image & create container -> verify -> if success, stop/remove old container -> update MongoDB.
        If replacement fails, existing working deployment remains untouched.
        """
        async def report(msg: str):
            if status_callback:
                try:
                    await status_callback(msg)
                except Exception:
                    pass

        if not DockerManager.is_docker_available():
            return False, "❌ Docker Engine is unavailable on this host."

        async with _DEPLOYMENT_LOCK:
            if project_id in _ACTIVE_DEPLOYMENTS:
                return False, "⚠️ This project is already being deployed."
            _ACTIVE_DEPLOYMENTS.add(project_id)

        try:
            existing_project = await Database.get_project(project_id)
            if not existing_project:
                return False, f"❌ Project ID {project_id} not found."

            old_image_name = existing_project["image_name"]
            old_container_name = existing_project["container_name"]
            env_vars = existing_project.get("env_vars", {})

            # Temp extraction dir for new zip
            deployments_base = os.path.abspath("deployments")
            temp_extract_dir = os.path.join(deployments_base, f"{project_id}_temp")
            final_extract_dir = existing_project.get("deployment_path", os.path.join(deployments_base, project_id))

            await report("📤 Processing new ZIP file...")
            try:
                ZipManager.validate_and_extract_zip(zip_file_path, temp_extract_dir)
            except ZipValidationError as ve:
                ZipManager.cleanup_dir(temp_extract_dir)
                return False, f"❌ New ZIP Validation Error: {str(ve)}"

            context_dir, error = ZipManager.find_dockerfile_context(temp_extract_dir)
            if error:
                ZipManager.cleanup_dir(temp_extract_dir)
                return False, error

            # Tag for temporary test build
            temp_image_name = f"{old_image_name}-new"
            temp_container_name = f"{old_container_name}-new"

            await report("🔨 Building new image...")
            build_success, build_msg = await DockerManager.build_image(context_dir, temp_image_name)
            if not build_success:
                ZipManager.cleanup_dir(temp_extract_dir)
                await Database.update_project(project_id, {"last_error": build_msg})
                return False, f"❌ Update failed.\n\n{build_msg}"

            await report("🚀 Testing new container startup...")
            start_success, start_msg, _ = await DockerManager.create_and_start_container(
                image_name=temp_image_name,
                container_name=temp_container_name,
                env_vars=env_vars
            )

            if not start_success:
                # Cleanup temp new container and image while keeping old container running untouched!
                await DockerManager.remove_container_and_image(temp_container_name, temp_image_name)
                ZipManager.cleanup_dir(temp_extract_dir)
                await Database.update_project(project_id, {"last_error": start_msg})
                return False, f"❌ Update failed.\n\n{start_msg}\n\nThe existing working deployment remains untouched."

            # SUCCESS! The new build is verified. Now swap old container with new container.
            await report("🔄 Swapping to new deployment...")

            # Clean up temporary test container
            await DockerManager.remove_container_and_image(temp_container_name, None)

            # Swap directory files
            ZipManager.cleanup_dir(final_extract_dir)
            shutil.move(temp_extract_dir, final_extract_dir)
            final_context_dir, _ = ZipManager.find_dockerfile_context(final_extract_dir)

            # Build final image tag and recreate container atomically
            await DockerManager.build_image(final_context_dir, old_image_name)
            await DockerManager.remove_container_and_image(None, temp_image_name)

            final_start, final_msg, _ = await DockerManager.create_and_start_container(
                image_name=old_image_name,
                container_name=old_container_name,
                env_vars=env_vars
            )

            if final_start:
                await Database.update_project(project_id, {
                    "zip_filename": zip_filename,
                    "status": "RUNNING",
                    "last_error": None
                })
                return True, "✅ Project replacement successful."
            else:
                await Database.update_project(project_id, {
                    "status": "FAILED",
                    "last_error": final_msg
                })
                return False, f"❌ Final container swap failed:\n{final_msg}"

        except Exception as e:
            logger.exception("Error during project replacement")
            return False, f"❌ Update failed with error: {str(e)}"
        finally:
            async with _DEPLOYMENT_LOCK:
                _ACTIVE_DEPLOYMENTS.discard(project_id)

    @classmethod
    async def redeploy_project(cls, project_id: str, status_callback=None) -> Tuple[bool, str]:
        """
        Redeploys project using its existing stored source path and environment variables.
        """
        async def report(msg: str):
            if status_callback:
                try:
                    await status_callback(msg)
                except Exception:
                    pass

        if not DockerManager.is_docker_available():
            return False, "❌ Docker Engine is unavailable on this host."

        async with _DEPLOYMENT_LOCK:
            if project_id in _ACTIVE_DEPLOYMENTS:
                return False, "⚠️ This project is already being deployed."
            _ACTIVE_DEPLOYMENTS.add(project_id)

        try:
            existing_project = await Database.get_project(project_id)
            if not existing_project:
                return False, f"❌ Project ID {project_id} not found."

            extract_dir = existing_project["deployment_path"]
            image_name = existing_project["image_name"]
            container_name = existing_project["container_name"]
            env_vars = existing_project.get("env_vars", {})

            if not os.path.exists(extract_dir):
                return False, f"❌ Deployment source files missing at {extract_dir}"

            context_dir, error = ZipManager.find_dockerfile_context(extract_dir)
            if error:
                return False, error

            await report("🔨 Rebuilding Docker image...")
            build_success, build_msg = await DockerManager.build_image(context_dir, image_name)
            if not build_success:
                await Database.update_project(project_id, {"last_error": build_msg})
                return False, f"❌ Docker build failed:\n{build_msg}"

            await report("🚀 Restarting container with updated build...")
            start_success, start_msg, _ = await DockerManager.create_and_start_container(
                image_name=image_name,
                container_name=container_name,
                env_vars=env_vars
            )

            if start_success:
                await Database.update_project(project_id, {
                    "status": "RUNNING",
                    "last_error": None
                })
                return True, "✅ Project redeployed successfully."
            else:
                await Database.update_project(project_id, {
                    "status": "FAILED",
                    "last_error": start_msg
                })
                return False, f"❌ Container startup failed:\n{start_msg}"

        except Exception as e:
            logger.exception("Error during redeployment")
            return False, f"❌ Redeployment failed: {str(e)}"
        finally:
            async with _DEPLOYMENT_LOCK:
                _ACTIVE_DEPLOYMENTS.discard(project_id)
