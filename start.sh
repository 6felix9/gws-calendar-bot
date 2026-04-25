#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

cd "$ROOT_DIR"

echo "========================================"
echo "  Environment Setup"
echo "========================================"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 is required but was not found in PATH." >&2
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "[INFO] Creating virtual environment at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
else
  echo "[INFO] Virtual environment already exists at $VENV_DIR"
fi

echo
echo "----------------------------------------"
echo "  Activating Virtual Environment"
echo "----------------------------------------"

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

echo "[INFO] Upgrading pip"
python -m pip install --upgrade pip

echo "[INFO] Installing dependencies"
python -m pip install -r requirements.txt

echo
echo "----------------------------------------"
echo "  Loading Environment Variables"
echo "----------------------------------------"

if [ -f "$ROOT_DIR/.env" ]; then
  echo "[INFO] Loading variables from .env"
  set -a
  # shellcheck source=/dev/null
  source "$ROOT_DIR/.env"
  set +a
elif [ -f "$ROOT_DIR/.env.example" ]; then
  echo "[ERROR] No .env file found. Create one from .env.example before starting the bot." >&2
  exit 1
fi

missing_vars=()
for var_name in TELEGRAM_BOT_TOKEN OPENAI_API_KEY; do
  if [ -z "${!var_name:-}" ]; then
    missing_vars+=("$var_name")
  fi
done

if [ "${#missing_vars[@]}" -gt 0 ]; then
  echo "[ERROR] Missing required environment variable(s): ${missing_vars[*]}" >&2
  exit 1
fi

echo
echo "========================================"
echo "  Starting Bot"
echo "========================================"

exec python -m bot.main