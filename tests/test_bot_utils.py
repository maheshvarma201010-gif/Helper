import pytest
import asyncio
from bot.utils.security import mask_secret, mask_env_vars
from bot.utils.docker_inspector import DockerInspector, DockerfileCheckResult
from bot.utils.formatter import format_deployment_preview, get_status_badge

def test_mask_secret():
    assert mask_secret("rnd_1234567890abcdef") == "rnd****def"
    assert mask_secret("ghp_1234567890abcdef") == "ghp****def"
    assert mask_secret("short") == "sh****"
    assert mask_secret("123") == "****"

def test_mask_env_vars():
    vars_dict = {
        "PORT": "8080",
        "DATABASE_URL": "mongodb+srv://admin:pass@cluster.mongodb.net/db",
        "API_KEY": "rnd_9876543210"
    }
    masked = mask_env_vars(vars_dict)
    assert masked["PORT"] == "8080"
    assert "****" in masked["DATABASE_URL"]
    assert "****" in masked["API_KEY"]

def test_docker_inspector_parse_url():
    owner, repo = DockerInspector.parse_github_url("https://github.com/myorg/myrepo.git")
    assert owner == "myorg"
    assert repo == "myrepo"

    owner_short, repo_short = DockerInspector.parse_github_url("myorg/myrepo")
    assert owner_short == "myorg"
    assert repo_short == "myrepo"

def test_docker_inspector_validate():
    valid_df = "FROM python:3.12-slim\nWORKDIR /app\nCMD [\"python\", \"main.py\"]"
    res = DockerInspector.validate_dockerfile(valid_df)
    assert res.is_valid is True
    assert len(res.errors) == 0

    invalid_df = "RUN pip install -r requirements.txt"
    res_inv = DockerInspector.validate_dockerfile(invalid_df)
    assert res_inv.is_valid is False
    assert any("FROM" in err for err in res_inv.errors)

def test_docker_inspector_fix():
    bad_df = "RUN pip install -r requirements.txt\nCOPY . ."
    fixed, diff = DockerInspector.fix_dockerfile(bad_df, "python")
    assert "FROM python:3.12-slim" in fixed
    assert "CMD [" in fixed
    assert "---" in diff or "a/Dockerfile" in diff

def test_formatter_preview():
    docker_cfg = {
        "name": "my-docker-app",
        "type": "web_service",
        "repo": "https://github.com/owner/repo",
        "branch": "main",
        "is_docker": True,
        "dockerfilePath": "./Dockerfile",
        "dockerContext": ".",
        "env_vars": {"ENV": "prod"}
    }
    preview = format_deployment_preview(docker_cfg)
    assert "🐳 Dockerfile" in preview
    assert "Dockerfile Path" in preview
    assert "Build Command" not in preview
    assert "Start Command" not in preview

def test_status_badges():
    assert get_status_badge("live") == "🟢 RUNNING"
    assert get_status_badge("deploying") == "🔄 DEPLOYING"
    assert get_status_badge("build_failed") == "🔴 FAILED"
    assert get_status_badge("suspended") == "⚪ STOPPED"

@pytest.mark.asyncio
async def test_docker_inspector_branches_empty_on_failure():
    branches = await DockerInspector.fetch_repo_branches("nonexistent_user_12345", "nonexistent_repo_67890")
    assert branches == []
