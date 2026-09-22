#!/bin/bash
set -e

echo "=== CodeZen Backend Setup ==="

if ! command -v python3.11 &> /dev/null; then
    echo "ERROR: Python 3.11 required. Install via pyenv."
    exit 1
fi

echo "[1/5] Creating virtual environment..."
python3.11 -m venv venv
source venv/bin/activate

echo "[2/5] Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "[3/5] Starting Docker services (PostgreSQL + Redis + ChromaDB)..."
docker-compose up -d
echo "Waiting for services to be ready..."
sleep 8

echo "[4/5] Running Alembic migrations..."
alembic upgrade head

echo "[5/5] Starting FastAPI server..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

echo "=== CodeZen backend running at http://localhost:8000 ==="
echo "=== API docs at http://localhost:8000/docs ==="
