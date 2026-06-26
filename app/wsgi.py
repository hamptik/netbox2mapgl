"""WSGI entry point for gunicorn: ``gunicorn app.wsgi:application``."""

from __future__ import annotations

from app import create_app

application = create_app()
