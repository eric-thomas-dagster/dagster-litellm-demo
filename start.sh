#!/bin/bash
# Start Dagster webserver for LiteLLM demo

# Check if .env exists
if [ ! -f .env ]; then
    echo "No .env file found. Please create one from .env.example"
    echo "  cp .env.example .env"
    echo "  # Then edit .env and add your API key"
    exit 1
fi

# Load environment variables
set -a
source .env
set +a

# Start Dagster with dg dev
echo "Starting Dagster webserver with dg dev..."
echo "Open http://localhost:3000 when ready"
echo ""
dg dev
