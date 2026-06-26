# netbox2mapgl

A service that synchronizes topology from [NetBox](https://netbox.dev/) into data
for a [MapGL](https://grafana.com/) Grafana plugin map (links and paths to
backbone nodes). It polls the NetBox API, caches the results in a local SQLite
database, and exposes two JSON endpoints consumed by the map plugin frontend.

## NetBox setup

This service expects specific objects and fields to be configured in NetBox
(device roles, tags, geo custom fields, etc.). See **[NETBOX_SETUP.md](NETBOX_SETUP.md)**
for a detailed, step-by-step guide.

## Endpoints

| Method | Path       | Description                                                            |
|--------|------------|------------------------------------------------------------------------|
| GET    | `/links`   | Links between routers/switches + location markers                      |
| GET    | `/paths`   | Shortest paths from each node/VM to the nearest backbone node          |
| GET    | `/health`  | Cache status (object counts, last update time)                         |

All endpoints support an optional `?location=<slug>` query parameter for
filtering by location.

## Run with Docker Compose

1. Copy `.env.example` to `.env` and fill in the values:

   ```bash
   cp .env.example .env
   $EDITOR .env
   ```

2. Start the container:

   ```bash
   docker compose up -d --build
   ```

3. Check the health:

   ```bash
   curl http://localhost:5000/health
   ```

The application starts immediately and a background thread then refreshes the
data from NetBox at a `CACHE_INTERVAL_SEC` interval. The SQLite file is stored
in the `netbox2mapgl_data` volume (path `/data/netbox_cache.db` inside the
container).

## Build and publish the image

```bash
docker build -t ghcr.io/<owner>/netbox2mapgl:latest .
docker push ghcr.io/<owner>/netbox2mapgl:latest
```

## Local development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt

# lint, types, tests
ruff check app tests run.py
ruff format --check app tests run.py
mypy app
pytest

# run the dev server (requires NETBOX_URL, NETBOX_TOKEN in the environment)
DB_PATH=/tmp/netbox_cache.db python run.py
```

## Architecture

```
app/
├── config.py      # configuration from env with validation
├── db.py          # SQLite layer (WAL, JSON text, no external dependencies)
├── netbox.py      # NetBox API client (requests.Session)
├── cache.py       # thread-safe cache store (snapshot/update)
├── refresh.py     # background thread syncing NetBox -> DB -> cache
├── builders/
│   ├── links.py   # build /links
│   ├── paths.py   # build /paths (BFS to the nearest backbone node)
│   └── utils.py   # shared helpers (speed, coordinates, roles)
├── routes.py      # Flask blueprint (/links, /paths, /health)
├── __init__.py    # create_app() factory
└── wsgi.py        # gunicorn entrypoint: app.wsgi:application
```

The cache is stored in SQLite (WAL mode for concurrent reads during writes).
`sqlite3` ships with Python's standard library, so there are no external
database dependencies — only a Docker volume is needed for DB file persistence.

The background refresh thread is started only through `create_app()` (not at
import time). The production configuration uses a single gunicorn worker
(`gunicorn -w 1`) so the refresh thread runs in a single instance.

## Environment variables

| Variable                      | Required | Default                 | Description                                |
|-------------------------------|----------|-------------------------|--------------------------------------------|
| `NETBOX_URL`                  | yes      |                         | Base URL of NetBox                         |
| `NETBOX_TOKEN`                | yes      |                         | NetBox API token                           |
| `DB_PATH`                     | no       | `/data/netbox_cache.db` | Path to the SQLite cache file              |
| `NETBOX_VERIFY_SSL`           | no       | `true`                  | Verify the NetBox SSL certificate          |
| `NETBOX_REQUEST_TIMEOUT`      | no       | `300`                   | NetBox request timeout, seconds            |
| `NETBOX_PAGE_SIZE`            | no       | `1000`                  | NetBox API pagination page size            |
| `LISTEN_HOST` / `LISTEN_PORT` | no       | `0.0.0.0` / `5000`      | Dev server address/port                    |
| `CACHE_INTERVAL_SEC`          | no       | `1200`                  | Cache refresh interval, seconds            |
| `TRACE_CONCURRENCY`           | no       | `1`                     | Trace request parallelism                  |
| `BLANK_LINES_BETWEEN_OBJECTS` | no       | `3`                     | Blank lines between objects in `/paths`    |
| `LOG_LEVEL`                   | no       | `INFO`                  | Log level                                  |
