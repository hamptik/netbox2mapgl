# NetBox setup guide

This document describes every object and field that `netbox2mapgl` reads from
NetBox. Configure the items below before (or alongside) starting the service —
the builders will only emit data for objects that match these rules.

> The service only needs **read** access to NetBox. Create a dedicated API token
> with read-only permissions.

---

## 1. API token

Create an API token in NetBox under **Admin → Users → API Tokens** (or per-user
on the user's profile page).

- The token needs read access to the **DCIM** and **Virtualization** endpoints
  listed in [section 8](#8-endpoints-used).
- Grant the **minimum scope** required (read-only is sufficient).
- Provide the token via the `NETBOX_TOKEN` environment variable and the NetBox
  base URL via `NETBOX_URL`.

---

## 2. Device roles

`netbox2mapgl` only traces links between devices whose **role slug** is one of:

| Role slug | Description                                   |
|-----------|-----------------------------------------------|
| `router`  | Routers                                       |
| `switch`  | Switches                                      |

These are matched against the device's `role` (NetBox ≥ 2.11) or the legacy
`device_role` field. Devices with any other role (e.g. `server`, `firewall`,
`ap`) are ignored by the link builder and will not appear as link endpoints.

The set of accepted role slugs is configurable via the `NETBOX_TARGET_ROLES`
environment variable (a JSON array). The default is `["router","switch"]`.

**Action:** ensure every device you want on the map has a role that matches
`NETBOX_TARGET_ROLES`. If you use a different role slug (e.g. `core-switch`),
either rename the slug to match or set `NETBOX_TARGET_ROLES` accordingly.

---

## 3. Tag `mapgl-main` (backbone nodes)

The `/paths` builder computes the shortest path from every node to the nearest
**backbone (main) node**. A node is considered a backbone node when it has the
tag:

```
mapgl-main
```

The tag slug is configurable via the `NETBOX_MAIN_TAG` environment variable
(default: `mapgl-main`).

The tag is matched by **slug**, so create a tag whose slug matches the
configured value:

- **Customization → Tags → + Add**
- Name: e.g. `MapGL Main`
- Slug: `mapgl-main` (or whatever you set in `NETBOX_MAIN_TAG`)

Then apply this tag to every device that should be treated as a backbone/core
destination. At least one tagged device must be reachable from other devices
through cabled interfaces, otherwise no paths are produced.

---

## 4. Location custom fields `lat` and `lon`

Coordinates are read from **custom fields** attached to NetBox locations. The
service reads two custom fields whose names are configurable via the
`NETBOX_LAT_FIELD` and `NETBOX_LON_FIELD` environment variables (defaults:
`lat` and `lon`).

| Custom field | Env var           | Default | Stores     |
|--------------|-------------------|---------|------------|
| `lat`        | `NETBOX_LAT_FIELD`| `lat`   | Latitude   |
| `lon`        | `NETBOX_LON_FIELD`| `lon`   | Longitude  |

**Action:**

1. Go to **Customization → Custom Fields → + Add**.
2. Create a custom field with:
   - Type: **Decimal** (or Text)
   - Object type: **DCIM > Location** (apply to locations)
   - Name: `lat` (or whatever you set in `NETBOX_LAT_FIELD`)
3. Repeat for `lon` (or `NETBOX_LON_FIELD`).
4. For every location that should appear on the map, fill in the latitude in
   the lat field and the longitude in the lon field.

Locations without both coordinates (or with `0`) are **skipped** — no markers
and no links are emitted for them.

---

## 5. Device location assignment

Each device that appears in `/links` **must** have a **Location** assigned
(which itself must have coordinates, see [section 4](#4-location-custom-fields-geocoord_x-and-geocoord_y)).

- The link builder reads `device.location.id` to look up the location object and
  its coordinates.
- Devices without a location, or whose location has no coordinates, are skipped.
- Links are only emitted between devices in **different** locations; two devices
  in the same location produce no link record.

---

## 6. Cables and interfaces

Links and paths are derived from NetBox **cable traces**.

- **Cables** must connect interfaces between two devices (`/api/dcim/cables/`).
  Power cables are filtered out automatically.
- **Interfaces** are fetched from `/api/dcim/interfaces/`. Only interfaces that
  have a `cable` reference are traced.
- The trace is performed via NetBox's built-in
  `/api/dcim/interfaces/<id>/trace/` endpoint.

**Link capacity (speed)** is parsed from the interface name and/or the cable
type field. Patterns like `10gbase`, `1gbase`, `1000base`, `10base` are
recognized (case-insensitive). For example an interface named `TenGigE0/0/0`
or a cable type `10gbase-t` yields a 10 Gbps capacity. When no speed can be
parsed, the capacity is reported as `0`.

**Action:** ensure the physical topology is modeled with cables between
interfaces in NetBox. Connect:

```
Device A [interface] --cable-- [interface] Device B
```

---

## 7. Virtual chassis, clusters and virtual machines

### Virtual chassis

When a device is a member of a **virtual chassis**, the map uses the virtual
chassis name as the device's display name (instead of the individual member
name). This keeps multi-member chassis represented by a single label.

- No special action is required beyond creating the virtual chassis and naming
  it in NetBox. If a device has no virtual chassis, its own `name` is used.

### Clusters (virtualization)

For VM path calculation, group the relevant physical hosts (devices) into a
**cluster** under **Virtualization → Clusters**.

- Devices with a `cluster` assignment are grouped by cluster name.
- Each cluster gets a representative path to the backbone through one of its
  member devices.

### Virtual machines

Virtual machines are read from `/api/virtualization/virtual-machines/`.

- A VM must be assigned to a **cluster** to receive a path.
- The VM path is constructed as `[VM → cluster → … → main node]`.
- VMs without a cluster are skipped.

**Action:** to see VMs on the map, assign them to a cluster whose member devices
have cabled links to the rest of the topology.

---

## 8. Endpoints used

The service reads the following NetBox REST API endpoints (all read-only):

| Endpoint                                       | Used for                          |
|------------------------------------------------|-----------------------------------|
| `GET /api/dcim/locations/`                     | Locations + coordinates           |
| `GET /api/dcim/devices/`                       | Devices, roles, tags, clusters    |
| `GET /api/virtualization/virtual-machines/`    | Virtual machines                  |
| `GET /api/dcim/cables/?type__n=power`          | Cables (power cables excluded)    |
| `GET /api/dcim/interfaces/`                    | Interfaces                        |
| `GET /api/dcim/interfaces/<id>/trace/`         | Per-interface cable trace         |

Pagination is handled automatically via `offset`/`limit` (see `NETBOX_PAGE_SIZE`)
so a server-side `MAX_PAGE_SIZE` cap will not truncate the result set.

---

## Checklist

- [ ] Read-only API token created (`NETBOX_TOKEN`).
- [ ] `NETBOX_URL` points to the NetBox instance.
- [ ] Target devices have a role slug listed in `NETBOX_TARGET_ROLES` (default: `router`, `switch`).
- [ ] Backbone devices tagged with `NETBOX_MAIN_TAG` (default: `mapgl-main`).
- [ ] Locations have `NETBOX_LAT_FIELD` (latitude, default: `lat`) and `NETBOX_LON_FIELD` (longitude, default: `lon`) filled.
- [ ] Devices assigned to a geo-tagged location.
- [ ] Cables connect interfaces between devices.
- [ ] (Optional) Virtual machines assigned to clusters of cabled devices.
