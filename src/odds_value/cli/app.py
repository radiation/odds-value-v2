from __future__ import annotations

import typer

from odds_value.cli.features import app as features_app
from odds_value.cli.ingest import app as ingest_app
from odds_value.cli.seed_provider_data import app as provider_data_app

app = typer.Typer(no_args_is_help=True)
app.add_typer(provider_data_app, name="seed-provider-data")
app.add_typer(ingest_app, name="ingest")
app.add_typer(features_app, name="features")
