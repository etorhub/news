#!/usr/bin/env bash
set -e
docker compose exec worker python -m app.worker_cli run-pipeline
