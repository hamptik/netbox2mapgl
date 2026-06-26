# Grafana setup guide

This document walks through configuring Grafana to display network topology
maps powered by `netbox2mapgl`. You will install the panel plugin, configure
datasources, create dashboard variables, and import the ready-made panel
templates.

> Prerequisites: `netbox2mapgl` is already running and reachable from Grafana
> (see the [main README](README.md)). NetBox is configured per
> [NETBOX_SETUP.md](NETBOX_SETUP.md).

---

## 1. Install the MapGL panel plugin

The maps use the **MapGL panel** plugin (`vaduga-mapgl-panel`).

**Option A — Grafana CLI**

```bash
grafana-cli plugins install vaduga-mapgl-panel
systemctl restart grafana-server
```

**Option B — Grafana plugins page**

Navigate to **Configuration → Plugins** in Grafana, search for *MapGL*, and
click **Install**.

After installation, verify the plugin appears under **Plugins** as *MapGL
Panel*.

---

## 2. Configure the Infinity datasource

The panels fetch topology JSON (links and paths) from the `netbox2mapgl`
service via the **Infinity** datasource.

### 2.1 Install Infinity

**Option A — Grafana CLI**

```bash
grafana-cli plugins install yesoreyeram-infinity-datasource
systemctl restart grafana-server
```

**Option B — Plugins page**

Search for *Infinity* under **Configuration → Plugins** and install it.

### 2.2 Create the datasource

1. Go to **Configuration → Data sources → Add data source**.
2. Select **Infinity**.
3. Set the following:

   | Field   | Value                                          |
   |---------|------------------------------------------------|
   | Name    | `netbox2mapgl` (or any name you prefer)        |
   | Type    | Infinity                                       |
   | URL     | `http://<netbox2mapgl-host>:5000`              |

   Replace `<netbox2mapgl-host>` with the address of your `netbox2mapgl`
   service (e.g. `localhost` if running on the same machine, or a container
   hostname / IP).

4. Click **Save & test**.

> The panel templates use relative paths (`/links`, `/paths`). The base URL
> configured here is automatically prepended, so panels do not need to
> hardcode the host address.

---

## 3. Configure Prometheus with SNMP metrics

Traffic and device-status overlays require a **Prometheus** datasource fed by
the [snmp_exporter](https://github.com/prometheus/snmp_exporter).

### 3.1 Install snmp_exporter

```bash
# Download the latest release
# https://github.com/prometheus/snmp_exporter/releases
tar xzf snmp_exporter-*.tar.gz
cd snmp_exporter-*
./snmp_exporter --config.file=snmp.yml
```

The default `snmp.yml` ships with the required OIDs. Verify that the following
metrics are present in the module you use (typically `if_mib`):

| Metric           | OID                         | Description                      |
|------------------|-----------------------------|----------------------------------|
| `ifHCInOctets`   | 1.3.6.1.2.1.31.1.1.1.6      | 64-bit incoming traffic counter  |
| `ifHCOutOctets`  | 1.3.6.1.2.1.31.1.1.1.10     | 64-bit outgoing traffic counter  |
| `ifDescr`        | 1.3.6.1.2.1.2.2.1.2         | Interface description            |
| `ifIndex`        | 1.3.6.1.2.1.2.2.1.1         | Interface index                  |

### 3.2 Configure Prometheus scrape jobs

Add a scrape job for your network devices:

```yaml
scrape_configs:
  - job_name: 'network'
    scrape_interval: 60s
    static_configs:
      - targets:
          - 192.168.1.1     # router 1
          - 192.168.1.2     # router 2
          # ... add all SNMP-managed devices
    params:
      module: [if_mib]
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: snmp-exporter:9116  # snmp_exporter address
```

> The panel templates filter by `job=~".*network.*"`. Adjust the job name to
> match your configuration, or rename the job to include `network`.

### 3.3 (Optional) Blackbox exporter for probe_success

The geographic map uses `probe_success` to determine device status. If you use
the [Blackbox exporter](https://github.com/prometheus/blackbox_exporter), add:

```yaml
  - job_name: 'blackbox'
    metrics_path: /probe
    params:
      module: [icmp]
    static_configs:
      - targets:
          - 192.168.1.1
          - 192.168.1.2
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: blackbox-exporter:9115
```

### 3.4 Prometheus datasource in Grafana

1. Go to **Configuration → Data sources → Add data source**.
2. Select **Prometheus**.
3. Set the URL to your Prometheus server (e.g. `http://prometheus:9090`).
4. Click **Save & test**.

---

## 4. Create dashboard variables

Before importing the panels, create the following variables in your dashboard.
Open **Dashboard settings → Variables** and add each one:

| Variable               | Type        | Description                                                       |
|------------------------|-------------|-------------------------------------------------------------------|
| `DS_INFINITY`          | Data source | Select the Infinity datasource (netbox2mapgl)                     |
| `DS_PROMETHEUS`        | Data source | Select the Prometheus datasource                                  |
| `location`             | Text box    | Location slug filter (used by the local map). Leave empty for all.|
| `LOCAL_MAP_UID`        | Text box    | Dashboard UID of the local map (for drill-down from geographic map) |
| `DEVICE_DASHBOARD_UID` | Text box    | Dashboard UID of the device detail dashboard (for drill-down)     |

### Variable configuration details

**DS_INFINITY** (Data source type):

- Name: `DS_INFINITY`
- Type: **Data source**
- Data source type: **Infinity**

**DS_PROMETHEUS** (Data source type):

- Name: `DS_PROMETHEUS`
- Type: **Data source**
- Data source type: **Prometheus**

**location** (Text box):

- Name: `location`
- Type: **Text box**
- Default value: *(empty)*
- Used in the local map panel to filter by NetBox location slug.

**LOCAL_MAP_UID** (Text box):

- Name: `LOCAL_MAP_UID`
- Type: **Text box**
- Default value: the UID of your local map dashboard (found in the URL:
  `/d/<UID>/...`)

**DEVICE_DASHBOARD_UID** (Text box):

- Name: `DEVICE_DASHBOARD_UID`
- Type: **Text box**
- Default value: the UID of your device detail dashboard

---

## 5. Import panel templates

Ready-made panel JSON files are available in the [`panels/`](panels/) folder:

| File           | Description                                                    |
|----------------|----------------------------------------------------------------|
| `geomap.json`  | Geographic network map showing inter-location links and traffic|
| `localmap.json`| Logical/local map showing device-to-backbone paths             |

### Import method

1. Download the JSON file(s) from the
   [`panels/` folder on GitHub](panels/).
2. In your Grafana dashboard, add a new panel and open the panel editor.
3. In the panel editor, change the visualization type to **MapGL Panel**.
4. Click the **panel JSON** icon (or use the panel menu → **More → Import
   panel model**).
5. Paste the contents of the downloaded JSON file.
6. Click **Apply**.

> Alternatively, you can copy the JSON content and paste it directly into the
> panel's JSON editor.

---

## 6. Configure panels after import

After importing, verify the following settings match your environment:

### 6.1 Datasource variables

The panels reference `${DS_INFINITY}` and `${DS_PROMETHEUS}`. Make sure the
dashboard variables from [section 4](#4-create-dashboard-variables) are
configured correctly.

### 6.2 Infinity query paths

The panels use relative URL paths:

- Geographic map: `/links`
- Local map: `/paths?location=${location}`

The base URL is taken from the Infinity datasource configuration. If your
`netbox2mapgl` service is behind a reverse proxy with a path prefix, adjust
these accordingly (e.g. `/netbox2mapgl/links`).

### 6.3 Prometheus query adaptation

The panel templates include example PromQL queries for SNMP traffic metrics.
Review and adapt the job name filters (`job=~".*network.*"`,
`job=~".*snmp.*"`) to match your Prometheus configuration.

**Geographic map queries:**

| RefId | Purpose                              | Key metric         |
|-------|--------------------------------------|--------------------|
| B     | Incoming traffic rate per interface  | `ifHCInOctets`     |
| D     | Outgoing traffic rate per interface  | `ifHCOutOctets`    |
| C     | Device availability status           | `probe_success`    |

**Local map query:**

| RefId | Purpose                              | Key metric                |
|-------|--------------------------------------|---------------------------|
| B     | Device up/down ratio                 | `up` / `probe_success`    |

### 6.4 Map view coordinates

After import, the map starts at a world view (lat 0, lon 0, zoom 1). Pan and
zoom to your network's geographic area, then save the dashboard.

---

## 7. Set up drill-down navigation

The panels include data links for navigation between dashboards:

### Geographic map → Local map

Clicking a node on the geographic map opens the local map filtered to that
location. This uses the `${LOCAL_MAP_UID}` variable.

- Create a separate dashboard containing the **Local Network Map** panel.
- Copy its UID from the URL (`/d/<UID>/...`).
- Set the `LOCAL_MAP_UID` variable to that UID.

### Local map → Device dashboard

Clicking a device on the local map opens a device detail dashboard. This uses
the `${DEVICE_DASHBOARD_UID}` variable.

- Create or use an existing device detail dashboard that accepts a
  `${instance}` variable.
- Set the `DEVICE_DASHBOARD_UID` variable to that dashboard's UID.

---

## Checklist

- [ ] MapGL panel plugin installed (`vaduga-mapgl-panel`).
- [ ] Infinity datasource installed and configured with `netbox2mapgl` URL.
- [ ] snmp_exporter installed with `if_mib` module.
- [ ] Prometheus scraping network devices (job name includes `network`).
- [ ] (Optional) Blackbox exporter for `probe_success`.
- [ ] Prometheus datasource added in Grafana.
- [ ] Dashboard variables created (`DS_INFINITY`, `DS_PROMETHEUS`,
      `location`, `LOCAL_MAP_UID`, `DEVICE_DASHBOARD_UID`).
- [ ] Panel JSON files imported from `panels/`.
- [ ] Map view adjusted to your network area.
- [ ] Drill-down links tested (geographic → local → device).
