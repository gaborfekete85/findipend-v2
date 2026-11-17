import shutil
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command
from tests.conftest import BACKEND


def _config_with_versions_in(versions: Path) -> Config:
    skip_cache = shutil.ignore_patterns("__pycache__")
    shutil.copytree(BACKEND / "alembic" / "versions", versions, ignore=skip_cache)
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("version_locations", str(versions))
    return config


def _new_revision_file(versions: Path) -> Path:
    new = [p for p in versions.glob("*.py") if p.name != "0001_create_trade_tables.py"]
    assert len(new) == 1, new
    return new[0]


def test_revision_writes_a_file_chained_to_0001(tmp_path):
    versions = tmp_path / "versions"
    config = _config_with_versions_in(versions)

    script = command.revision(config, message="probe")

    path = _new_revision_file(versions)
    assert path.name == f"{script.revision}_probe.py"
    source = path.read_text()
    assert 'down_revision = "0001"\n' in source
    assert f'revision = "{script.revision}"\n' in source
    loaded = ScriptDirectory.from_config(config).get_revision(script.revision)
    assert loaded.down_revision == "0001"
    assert ScriptDirectory.from_config(config).get_heads() == [script.revision]


def test_generated_revision_passes_ruff(tmp_path):
    versions = tmp_path / "versions"
    command.revision(_config_with_versions_in(versions), message="probe")
    path = _new_revision_file(versions)

    config = str(BACKEND / "pyproject.toml")
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--config", config, str(path)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
