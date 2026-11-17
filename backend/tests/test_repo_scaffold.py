import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _env_example() -> dict[str, str]:
    path = REPO_ROOT / ".env.example"
    assert path.is_file(), f"{path} is missing"
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def test_env_example_lists_required_keys_with_placeholders():
    values = _env_example()

    for key in ("CLERK_PUBLISHABLE_KEY", "CLERK_SECRET_KEY", "CLERK_JWKS_URL", "DATABASE_URL"):
        assert key in values, key
        assert values[key] != "", key
    assert values["CLERK_PUBLISHABLE_KEY"] == "pk_test_placeholder"
    assert values["CLERK_SECRET_KEY"] == "sk_test_placeholder"


def test_gitignore_excludes_env_venv_and_pycache():
    path = REPO_ROOT / ".gitignore"
    assert path.is_file(), f"{path} is missing"
    patterns = {
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert {".env", ".venv/", "__pycache__/"} <= patterns


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not installed")
def test_docker_compose_config_lists_postgres_backend_and_frontend():
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    assert sorted(services) == ["backend", "frontend", "postgres"]
    published = [port["published"] for port in services["frontend"]["ports"]]
    assert published == ["3000"]


VITE_BUILD_VARS = {
    "VITE_CLERK_PUBLISHABLE_KEY": "pk_test_from_env",
    "VITE_API_BASE_URL": "http://api.from-env.test",
}


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not installed")
def test_docker_compose_passes_vite_vars_to_the_frontend_build():
    # Vite inlines VITE_* at build time and the image has no .env (PR #19, QA Q1).
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=REPO_ROOT,
        env={**os.environ, **VITE_BUILD_VARS},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    build = json.loads(result.stdout)["services"]["frontend"]["build"]
    assert build.get("args") == VITE_BUILD_VARS


def test_frontend_dockerfile_exposes_vite_vars_to_the_build():
    lines = [
        line.strip() for line in (REPO_ROOT / "frontend" / "Dockerfile").read_text().splitlines()
    ]
    build_at = lines.index("RUN bun run build")

    for name in VITE_BUILD_VARS:
        assert f"ARG {name}" in lines[:build_at], name


def test_frontend_lockfile_is_bun_lock_only():
    frontend = REPO_ROOT / "frontend"

    assert (frontend / "package.json").is_file()
    assert (frontend / "bun.lock").is_file()
    assert not (frontend / "package-lock.json").exists()
