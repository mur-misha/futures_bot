#!/bin/bash

cd "$(dirname "$0")"

# Telegram credentials are loaded from .env (see config.py's _load_dotenv)
# or from real environment variables. Never hardcode secrets here.
# If you don't have a .env yet: cp .env.example .env  and fill it in.

source venv/bin/activate

exec python3 futures_volume_screener.py
