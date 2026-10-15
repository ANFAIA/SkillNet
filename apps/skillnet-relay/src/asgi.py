"""Entry point for uvicorn: ``uvicorn src.asgi:app``."""

from src.main import create_app

app = create_app()
