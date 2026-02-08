from __future__ import annotations

from typer.testing import CliRunner

from odds_value.cli.app import app


def test_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    # Basic sanity checks that a top-level command is registered.
    assert "seed-provider-data" in result.stdout
