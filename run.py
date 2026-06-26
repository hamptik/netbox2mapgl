"""Local development entry point: ``python run.py``.

Production uses gunicorn (``gunicorn app.wsgi:application``) instead.
"""

from __future__ import annotations

from app import create_app
from app.config import Config

config = Config.from_env()
app = create_app(config)


if __name__ == "__main__":
    app.run(host=config.listen_host, port=config.listen_port, debug=False)
