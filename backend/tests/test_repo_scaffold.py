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
def test_docker_compose_config_lists_postgres_and_backend():
    result = subprocess.run(
        ["docker", "compose", "config", "--services"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert sorted(result.stdout.split()) == ["backend", "postgres"]
