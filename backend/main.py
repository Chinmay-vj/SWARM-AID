"""ASGI entry point: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

Settings come from SWARM_* environment variables or .env. SWARM_JWT_SECRET is mandatory.
"""

from backend.application import create_app

app = create_app()
