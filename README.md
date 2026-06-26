# netbox2mapgl

A service that synchronizes topology from [NetBox](https://netbox.dev/) into data
for a [MapGL](https://grafana.com/) Grafana plugin map (links and paths to
backbone nodes). It polls the NetBox API, caches the results in a local SQLite
database, and exposes two JSON endpoints consumed by the map plugin frontend.

## Quick start

### Step 1 — Configure NetBox

The service reads device roles, tags, cables, and geo custom fields from
NetBox. See **[NETBOX_SETUP.md](NETBOX_SETUP.md)** for a detailed,
step-by-step guide covering API tokens, device roles, the `mapgl-main` tag,
location coordinates, cables, and virtual machines.

### Step 2 — Deploy the service

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

### Step 3 — Set up Grafana

Once the service is running, configure Grafana to visualize the topology:

1. **Install the MapGL panel plugin** (`vaduga-mapgl-panel`).
2. **Configure datasources**:
   - [Infinity](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/)
     — points to the `netbox2mapgl` service.
   - **Prometheus** with [snmp_exporter](https://github.com/prometheus/snmp_exporter)
     — provides interface traffic and device status metrics.
3. **Create dashboard variables** and **import panel templates** from the
   `panels/` folder.

See **[GRAFANA_SETUP.md](GRAFANA_SETUP.md)** for the complete walkthrough.

## Panel templates

Ready-made panel JSON files are available in the [`panels/`](panels/) folder:

| File           | Description                                                        |
|----------------|--------------------------------------------------------------------|
| `geomap.json`  | Geographic network map — inter-location links with traffic overlays|
| `localmap.json`| Logical/local map — device-to-backbone paths within a location     |

These templates are pre-configured with example transformations, thresholds,
and styling. They use dashboard variables (no hardcoded IPs or datasources), so
they work out of the box after following the [Grafana setup guide](GRAFANA_SETUP.md).

You can also download them directly from the
[`panels/` folder on GitHub](panels/).

## Endpoints

| Method | Path       | Description                                                            |
|--------|------------|------------------------------------------------------------------------|
| GET    | `/links`   | Links between routers/switches + location markers                      |
| GET    | `/paths`   | Shortest paths from each node/VM to the nearest backbone node          |
| GET    | `/health`  | Cache status (object counts, last update time)                         |

All endpoints support an optional `?location=<slug>` query parameter for
filtering by location.

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
