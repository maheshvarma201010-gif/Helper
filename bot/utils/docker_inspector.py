import re
import aiohttp
import logging
import difflib
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class DockerfileCheckResult:
    def __init__(self, is_valid: bool, errors: List[str], warnings: List[str], suggestions: List[str]):
        self.is_valid = is_valid
        self.errors = errors
        self.warnings = warnings
        self.suggestions = suggestions

class DockerInspector:
    @staticmethod
    def parse_github_url(url: str) -> Optional[Tuple[str, str]]:
        """Parses a GitHub URL into (owner, repo)."""
        pattern = r"github\.com/([^/]+)/([^/.]+)"
        match = re.search(pattern, url)
        if match:
            return match.group(1), match.group(2).rstrip(".git")
        return None

    @staticmethod
    async def fetch_repo_file(owner: str, repo: str, branch: str, filepath: str) -> Optional[str]:
        """Fetches raw file content from GitHub raw content CDN."""
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filepath.lstrip('/')}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(raw_url, timeout=10) as resp:
                    if resp.status == 200:
                        return await resp.text()
            except Exception as e:
                logger.warning(f"Failed to fetch {raw_url}: {e}")
        return None

    @staticmethod
    async def detect_dockerfiles(owner: str, repo: str, branch: str = "main") -> List[str]:
        """
        Detects Dockerfile paths in the repository using GitHub API or checking common locations.
        """
        api_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        detected = []
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(api_url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        tree = data.get("tree", [])
                        for item in tree:
                            path = item.get("path", "")
                            if item.get("type") == "blob":
                                filename = path.split("/")[-1]
                                if filename == "Dockerfile" or filename.startswith("Dockerfile."):
                                    detected.append(path)
            except Exception as e:
                logger.warning(f"GitHub API tree search failed: {e}")

        if not detected:
            # Fallback check standard root Dockerfile
            content = await DockerInspector.fetch_repo_file(owner, repo, branch, "Dockerfile")
            if content is not None:
                detected.append("Dockerfile")

        return detected

    @staticmethod
    def validate_dockerfile(content: str) -> DockerfileCheckResult:
        """
        Inspects Dockerfile instructions (FROM, RUN, COPY, WORKDIR, EXPOSE, CMD, ENTRYPOINT).
        Validates syntax and flags common issues.
        """
        errors = []
        warnings = []
        suggestions = []

        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]

        if not lines:
            return DockerfileCheckResult(False, ["Dockerfile is empty"], [], ["Add FROM and CMD instructions"])

        has_from = False
        has_cmd_or_entrypoint = False

        for i, line in enumerate(lines):
            upper_line = line.upper()
            if upper_line.startswith("FROM"):
                has_from = True
            elif upper_line.startswith("CMD") or upper_line.startswith("ENTRYPOINT"):
                has_cmd_or_entrypoint = True

            # Check for unquoted JSON format warnings in CMD/ENTRYPOINT
            if (upper_line.startswith("CMD") or upper_line.startswith("ENTRYPOINT")) and not line.strip().startswith("["):
                warnings.append(f"Line {i+1}: Consider using exec form [\"cmd\", \"arg\"] for {line.split()[0]}")

        if not has_from:
            errors.append("Missing 'FROM' instruction specifying a base image.")

        if not has_cmd_or_entrypoint:
            warnings.append("No 'CMD' or 'ENTRYPOINT' instruction found. Render service requires a process to execute.")

        is_valid = len(errors) == 0
        return DockerfileCheckResult(is_valid, errors, warnings, suggestions)

    @staticmethod
    def fix_dockerfile(content: str, project_type: str = "python") -> Tuple[str, str]:
        """
        Fixes genuine Docker-related problems in Dockerfile while preserving project logic.
        Returns (fixed_content, diff_text).
        """
        original_lines = content.splitlines()
        fixed_lines = list(original_lines)

        # Check if FROM is present
        has_from = any(line.strip().upper().startswith("FROM") for line in fixed_lines if not line.strip().startswith("#"))
        if not has_from:
            base_image = "python:3.12-slim" if project_type == "python" else "node:20-alpine"
            fixed_lines.insert(0, f"FROM {base_image}")
            fixed_lines.insert(1, "WORKDIR /app")

        # Check if CMD or ENTRYPOINT present
        has_cmd = any(line.strip().upper().startswith(("CMD", "ENTRYPOINT")) for line in fixed_lines if not line.strip().startswith("#"))
        if not has_cmd:
            if project_type == "python":
                fixed_lines.append('CMD ["python", "main.py"]')
            elif project_type == "node":
                fixed_lines.append('CMD ["npm", "start"]')
            else:
                fixed_lines.append('CMD ["sh", "-c", "echo Running service"]')

        fixed_content = "\n".join(fixed_lines) + "\n"

        # Generate Unified Diff
        diff = difflib.unified_diff(
            original_lines,
            fixed_lines,
            fromfile="a/Dockerfile",
            tofile="b/Dockerfile",
            lineterm=""
        )
        diff_text = "\n".join(list(diff))
        if not diff_text:
            diff_text = "No changes required."

        return fixed_content, diff_text

    @staticmethod
    def generate_dockerfile_template(project_type: str = "python") -> str:
        """Generates a default production-ready Dockerfile when none exists."""
        if project_type.lower() == "node":
            return (
                "FROM node:20-alpine\n"
                "WORKDIR /app\n"
                "COPY package*.json ./\n"
                "RUN npm install --production\n"
                "COPY . .\n"
                "EXPOSE 8080\n"
                "CMD [\"npm\", \"start\"]\n"
            )
        elif project_type.lower() == "go":
            return (
                "FROM golang:1.22-alpine AS builder\n"
                "WORKDIR /app\n"
                "COPY . .\n"
                "RUN go build -o main .\n"
                "FROM alpine:latest\n"
                "WORKDIR /app\n"
                "COPY --from=builder /app/main .\n"
                "EXPOSE 8080\n"
                "CMD [\"./main\"]\n"
            )
        else:  # Python
            return (
                "FROM python:3.12-slim\n"
                "WORKDIR /app\n"
                "COPY requirements.txt ./\n"
                "RUN pip install --no-cache-dir -r requirements.txt\n"
                "COPY . .\n"
                "EXPOSE 8080\n"
                "CMD [\"python\", \"-m\", \"bot\"]\n"
            )
