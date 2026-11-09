<p align="center">
  <img src="assets/logo.png" alt="RailFeed – Home Assistant integration" width="480">
</p>

# RailFeed for Home Assistant

[![hacs][hacs-badge]][hacs-url] [![Validate](https://github.com/torstenknoefel/ha-railfeed/actions/workflows/validate.yml/badge.svg)](https://github.com/torstenknoefel/ha-railfeed/actions/workflows/validate.yml) [![Tests](https://github.com/torstenknoefel/ha-railfeed/actions/workflows/tests.yml/badge.svg)](https://github.com/torstenknoefel/ha-railfeed/actions/workflows/tests.yml)

Live UK train departures for a station, from the free [RailFeed API](https://railfeed.co.uk/docs)
(built on Network Rail TRUST/Darwin feeds).

## Install

### HACS (recommended)

RailFeed is in the default HACS catalogue.

1. In Home Assistant open **HACS** and search for **RailFeed**.
2. Open it, click **Download**, and restart Home Assistant.

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=torstenknoefel&repository=ha-railfeed&category=integration)

If RailFeed doesn't show up in the search (for example because your HACS is out of date), add it as a custom
repository instead:

1. Open **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/torstenknoefel/ha-railfeed` with category **Integration**.
3. Search for **RailFeed**, download it, and restart Home Assistant.

### Manual

Copy `custom_components/railfeed` into your HA config folder's `custom_components/` directory and restart.

### Set up

1. Create a free account at <https://railfeed.co.uk>, then copy your key from
   <https://railfeed.co.uk/api-keys>.
2. **Settings → Devices & services → Add integration → RailFeed**. Enter your key.
3. On the next page choose your station by name: click the box and start typing, for example `belv`, and the
   list narrows to the matching stations (`Belvedere (BVD)`). You can also type the three-letter (CRS) code, e.g.
   `BVD`, `KGX` (King's Cross) or `WIM` (Wimbledon).
   Optionally choose a **calling at** station in the same way (see below).

The list of stations comes from RailFeed and is cached for a day. If it can't be loaded, the boxes become plain
text fields and you enter the three-letter codes instead.

Add the integration again for each extra station, or for the same station with a different
**calling at** station (one entry per station + destination pair; the same key can be reused).
For example `BVD` calling at `ABW` and `BVD` calling at `GNW` give two separate devices,
"Belvedere to Abbey Wood" and "Belvedere to Greenwich", each with its own sensors.

## Entities (per station)

| Entity | Meaning |
|---|---|
| Next departure | Timestamp of the next running train (expected time). Attributes carry full details + a `departures` list |
| Next destination / platform / delay / status | Details of that next train (`on_time`, `delayed`, `cancelled`) |
| Delayed services / Cancelled services | Counts across the departures kept on the board |

The `departures` attribute on **Next departure** is a list of dicts with `destination`, `scheduled_time`,
`expected_time`, `platform`, `status`, `delay_minutes`, `operator`, `cancel_reason`, `late_reason`, `coaches`, etc.
It is excluded from the recorder database.

### Attributes

**Every sensor also carries your configuration as attributes, all starting with `config_`**, so a template or
card can read a setting from any entity without you repeating it by hand:

| Attribute | Example | Setting |
|---|---|---|
| `config_station` | `BVD` | Station |
| `config_calling_at` | `ABW` | Only trains calling at |
| `config_via` | `["GNW", "LEW"]` | Show route as "via" these stations |
| `config_destinations` | `["KGX", "EDB"]` | Only trains to these destinations |
| `config_passenger_only` | `true` | Passenger trains only |
| `config_max_departures` | `10` | Departures to keep |
| `config_look_ahead_hours` | `2` | Look-ahead window (hours) |
| `config_update_interval_seconds` | `60` | Update interval (seconds) |

For example, the look-ahead window in a template:

```jinja
{{ state_attr('sensor.belvedere_to_abbey_wood_next_status', 'config_look_ahead_hours') }}
```

**See the [attribute reference](docs/attributes.md)** for every attribute of every sensor, with types, examples
and what each one means.

## Options (cog icon on the integration)

All of these are available as `config_*` attributes (see [Attributes](#attributes)).

- **Update interval**: default 60 s, minimum 30 s (RailFeed asks for no more than one poll per 30 s;
  limit is 60 requests/min per key).
- **Departures to keep** (default 10), **look-ahead window** (default 2 h).
- **Passenger trains only** (default on): hides freight, empty stock and charters.
- **Only trains calling at this station**: optional station on the train's route, e.g. Abbey Wood (`ABW`).
  Chosen when you add the entry (it is what makes the entry unique); to change it, add a new entry and remove the old one.
  (Entries created with v0.2.x keep it here in the options.)
  Only trains that stop there *after* your station are listed, whether or not it is their final destination.
  Each train also gets `calling_at_arrival` (advertised arrival time there) and `journey_minutes` attributes.
  This costs one extra API request per 15 minutes per entry (the answer is cached). Each entry also polls
  the live board, and the limit is 60 requests/min per key, so a handful of entries is fine.
- **Show route as "via" these stations**: optional, up to 5 stations picked by name, e.g. Greenwich and Lewisham (`GNW`, `LEW`).
  Use it when the same destination is reached by different routes (for example London Cannon Street via
  Greenwich *or* via Lewisham). Every train that calls at one of these stations gets it appended to its
  destination: `London Cannon Street via Greenwich`. The rules are the same for every route:
  a train is labelled with each via station it stops at after your station, in route order
  (`via Greenwich and Lewisham`); a train that only runs through the station is not labelled; and a train
  that *ends* at a via station is not labelled with it. Pick stations that every train on that route stops at.
  The label is in the `destination` attribute and in the *Next destination* sensor; the plain name is kept in
  `destination_name` and the list of stations in `via`. Each via station costs one cached API request per
  15 minutes per entry. If that lookup fails, the board still works, just without the label.
- **Destination filter**: optional stations the train's *final* destination must be, e.g. King's Cross and Edinburgh (`KGX`, `EDB`).
  Can be combined with the option above.

## Dashboard card

```yaml
type: markdown
title: Belvedere departures
content: |
  | Time | Destination | Plat | Status |
  |---|---|---|---|
  {% for d in state_attr('sensor.belvedere_next_departure', 'departures') or [] -%}
  | {{ d.scheduled_time }} | {{ d.destination }} | {{ d.platform or '-' }} | {{ 'Exp ' ~ d.expected_time if d.status == 'delayed' else ('Cancelled' if d.status == 'cancelled' else 'On time') }} |
  {% endfor %}
```

Adjust the entity id to match yours (it follows the station's device name).

## Tutorial: a departures board with flex-table-card

This builds a board for one route with five columns: **Due** (scheduled time), **Destination**
(with its "via" route), **Exp** (expected time), **Status** and **Left** (time until the expected time).
Status is coloured: **red** when cancelled, **green** when on time, **amber** with the minutes when the
train is running early or late. The card only appears when there is something to show. The example is a
south-east London route: trains from Belvedere (`BVD`) that call at Abbey Wood (`ABW`) and then run to London
Cannon Street either via Greenwich (`GNW`) or via Lewisham (`LEW`). Abbey Wood is only a *calling at* filter, not
the destination, so every train that stops there is listed whatever its final destination is. Replace the
stations with your own.

### 1. Install flex-table-card

It is a separate dashboard card. In HACS open **Frontend**, search for **flex-table-card**
(`custom-cards/flex-table-card`), download it and reload the browser.

### 2. Set up the route and the "via" stations

1. Add the integration with your station (example: Belvedere, `BVD`) and **Only trains calling at** Abbey Wood (`ABW`). That lists every train from Belvedere that stops at Abbey Wood, wherever it is going.
   (Leave it blank to list every train from your station.)
2. Open the integration's **Configure** (cog) and set **Show route as 'via' these stations** to Greenwich and
   Lewisham (`GNW`, `LEW`). Those trains, which end at London Cannon Street, now read *London Cannon Street via Greenwich* or
   *London Cannon Street via Lewisham*. Any other pair of routes works the same way: add a station that
   only one of the routes stops at.

### 3. Find your entity ids

Open **Settings → Devices & services → RailFeed**, pick the device and note its entity ids.
They follow the device name; for the example they would be:

| Entity | Used for |
|---|---|
| `sensor.belvedere_to_abbey_wood_next_departure` | holds the `departures` list the table is built from |
| `sensor.belvedere_to_abbey_wood_next_status` | tells the card whether a train is running |
| `sensor.belvedere_to_abbey_wood_cancelled_services` | tells the card whether any train is cancelled |

If yours differ, replace them in the YAML below.

### 4. Add the card

On your dashboard choose **Edit → Add card → Manual**, and paste:

```yaml
type: conditional
conditions:
  - condition: or
    conditions:
      - condition: state
        entity: sensor.belvedere_to_abbey_wood_next_status
        state_not:
          - unknown
          - unavailable
      - condition: numeric_state
        entity: sensor.belvedere_to_abbey_wood_cancelled_services
        above: 0
card:
  type: custom:flex-table-card
  title: 'Train: Belvedere → Abbey Wood'
  entities:
    include: sensor.belvedere_to_abbey_wood_next_departure
  css:
    thead tr th:nth-child(1): 'text-align: center;'
    thead tr th:nth-child(3): 'text-align: center;'
    thead tr th:nth-child(4): 'text-align: center;'
    thead tr th:nth-child(5): 'text-align: center;'
    tbody tr td:nth-child(1): 'white-space: nowrap;'
    tbody tr td:nth-child(3): 'white-space: nowrap;'
    tbody tr td:nth-child(2): 'white-space: nowrap; text-align: center;'
    tbody tr td:nth-child(4): 'white-space: nowrap; min-width: 5em; text-align: center;'
    tbody tr td:nth-child(5): 'white-space: nowrap; min-width: 5em; text-align: right;'
  columns:
    - name: Due
      data: departures
      modify: x.scheduled_time
    - name: Destination
      data: departures
      modify: |-
        (() => {
          const v = x.via || [];
          if (!v.length) return x.destination_name;
          const names = v.length > 1 ? v.slice(0, -1).join(', ') + ' and ' + v[v.length - 1] : v[0];
          return x.destination_name + '<br>via ' + names;
        })()
    - name: Exp
      data: departures
      modify: 'x.status == ''cancelled'' ? ''–'' : x.expected_time'
    - name: Status
      data: departures
      modify: |-
        (() => {
          if (x.status == 'cancelled') return '<span style="color:red">Cancelled</span>';
          const d = Math.round((new Date(x.expected) - new Date(x.scheduled)) / 60000);
          return d
            ? '<span style="color:#ffa000">' + d + ' min</span>'
            : '<span style="color:green">On time</span>';
        })()
    - name: Left
      data: departures
      modify: |-
        (() => {
          if (x.status == 'cancelled') return '–';
          const m = Math.round((new Date(x.expected) - Date.now()) / 60000);
          if (m <= 0) return 'now';
          return m >= 60 ? Math.floor(m / 60) + 'h ' + (m % 60) + ' min' : m + ' min';
        })()
```

How it works:

- **flex-table-card** reads the `departures` list from the sensor and builds one row per train. Each column
  has `data: departures`, and its `modify` expression gets the train as `x` and returns the cell's HTML.
- **Due** is the timetabled time (`x.scheduled_time`).
- **Destination** shows the destination name (`x.destination_name`) with the "via" route on a second line:
  `London Cannon Street` then `via Greenwich`. The line break is `<br>`, so the via text always starts on a
  new line. The route comes from the `via` list (several stations read `via Greenwich and Lewisham`). Trains
  without a via station show just the name. For the one-line form (`London Cannon Street via Greenwich`)
  use `x.destination` instead.
- **Exp** is the expected time exactly as the integration reports it (`x.expected_time`, from RailFeed's
  live data). Nothing is calculated from the delay. For a cancelled train it shows a dash.
- **Status** is coloured:
  - *Cancelled* in **red**.
  - *On time* in **green**.
  - Any difference between expected and due time is shown as a number and `min`, in **amber**. A train
    running late shows `8 min`; one running early keeps its minus sign, `-2 min`. The number is the expected
    time minus the due time, so early trains are covered too.
- **Left** is the time from now until the expected time: `13 min`, `1h 20 min`, or `now` once it is due.
  It is a dash for cancelled trains.
- **The conditional card** wraps the table and shows it only when at least one condition holds (`or`):
  the next train has a real status, or at least one service is cancelled. The second condition matters
  because when every listed train is cancelled there is no "next train", yet you still want to see them.
- The table length follows **Departures to keep** and **Look-ahead window** in the integration's options.
- **Column layout** comes from the `css:` block. Each key is a CSS selector for one column
  (`td:nth-child(4)` is the fourth). All cells stay on one line (`white-space: nowrap`), so the times,
  Status and Left never break, and the Destination's via line only breaks where the `<br>` is. Status and Left
  have a minimum width of `5em`, enough for `Cancelled`, `-12 min` and `1h 56 min`. Destination and Status are
  centred, Left is right-aligned, and the headers of Due, Exp, Status and Left are centred. Adjust the
  values if your screen needs something different.
- To change a colour, edit the `color:` value in the Status column (`red`, `green`, `#ffa000`).

**Note on "Left":** it is worked out in your browser each time the card redraws. The card redraws when the
sensor's data changes, which is at most once per **Update interval** (default 60 s) and only if something
about the departures changed, so the countdown can lag by a minute or more between updates.

A board might look like this (Status colours are shown in brackets):

| Due | Destination | Exp | Status | Left |
|---|---|---|---|---|
| 17:55 | London Cannon Street<br>via Greenwich | 18:03 | 8 min (amber) | 13 min |
| 18:00 | London Cannon Street<br>via Lewisham | – | Cancelled (red) | – |
| 18:10 | London Cannon Street<br>via Greenwich | 18:08 | -2 min (amber) | 18 min |
| 18:25 | London Cannon Street<br>via Lewisham | 18:25 | On time (green) | 35 min |

### 5. Optional: a message when there are no trains

Add a second conditional card beneath the first. It appears only when there is no running train
**and** nothing cancelled, so the two cards never show together:

```yaml
type: conditional
conditions:
  - condition: state
    entity: sensor.belvedere_to_abbey_wood_next_status
    state: unknown
  - condition: numeric_state
    entity: sensor.belvedere_to_abbey_wood_cancelled_services
    below: 1
card:
  type: markdown
  title: 'Train: Belvedere → Abbey Wood'
  content: >-
    {% set h = state_attr('sensor.belvedere_to_abbey_wood_next_status', 'config_look_ahead_hours') | int(2) %}
    No trains to Abbey Wood in the next {{ h }} hour{{ '' if h == 1 else 's' }}.
```

With a list of `conditions`, *all* of them must hold; the first card needed `or` to show on *either*.

The message takes the look-ahead window from the `config_look_ahead_hours` attribute, so it stays correct when
you change **Look-ahead window** in the integration's options: with the default it reads
*No trains to Abbey Wood in the next 2 hours.* The `| int(2)` is a fallback in case the attribute is missing.
Every RailFeed sensor has this attribute, so any of them works here.

### Tips

- **While you edit the dashboard, conditional cards are always visible.** Leave edit mode to check the
  conditions.
- One card per route: repeat the steps with the entity ids of your other entries.
- If a cell shows raw `<span …>` text instead of red, your flex-table-card version may be escaping HTML;
  update it from HACS.
- Prefer no extra card? A built-in markdown card can show the same table; see the *Dashboard card* section.

## Automation example: notify when your usual train is disrupted

```yaml
trigger:
  - platform: state
    entity_id: sensor.belvedere_next_status
    to: [delayed, cancelled]
condition:
  - condition: time
    after: "07:00:00"
    before: "09:00:00"
action:
  - service: notify.notify
    data:
      message: >
        {{ state_attr('sensor.belvedere_next_departure','scheduled_time') }} to
        {{ states('sensor.belvedere_next_destination') }} is {{ states('sensor.belvedere_next_status') }}
        ({{ states('sensor.belvedere_next_delay') }} min).
```

## Notes

- A train counts as "delayed" at 1+ minutes late (`DELAY_THRESHOLD_MINS` in `board.py`).
- "Calling at" uses the *scheduled* timetable (RailFeed's `/api/services`), so a train added at very short
  notice may not appear until that timetable lookup refreshes, and a train that skips the station today
  because of disruption still shows.
- "Via" labels use the same scheduled-timetable lookup as "calling at", so they share its limits.
- Platforms the operator has asked to keep off public screens are hidden.
- Data is attributed to RailFeed; not affiliated with National Rail.

## Development

```bash
pip install pytest
pytest          # parser tests, no Home Assistant needed
```

[hacs-badge]: https://img.shields.io/badge/HACS-Default-41BDF5.svg
[hacs-url]: https://hacs.xyz
