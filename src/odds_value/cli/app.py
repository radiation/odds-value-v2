from __future__ import annotations

import typer

from odds_value.cli.seed_provider_data import app as provider_data_app

app = typer.Typer(no_args_is_help=True)
app.add_typer(provider_data_app, name="seed-provider-data")
