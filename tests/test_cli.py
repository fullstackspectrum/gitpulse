from typer.testing import CliRunner

from gitpulse import __version__
from gitpulse.cli import app


def test_version_flag() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_missing_token_is_reported(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    result = CliRunner().invoke(app, ["repos"])

    assert result.exit_code == 1
    assert "No GitHub token found" in result.output
