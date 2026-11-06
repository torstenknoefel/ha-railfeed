# RailFeed for Home Assistant

[![hacs][hacs-badge]][hacs-url] [![Validate](https://github.com/torstenknoefel/ha-railfeed/actions/workflows/validate.yml/badge.svg)](https://github.com/torstenknoefel/ha-railfeed/actions/workflows/validate.yml) [![Tests](https://github.com/torstenknoefel/ha-railfeed/actions/workflows/tests.yml/badge.svg)](https://github.com/torstenknoefel/ha-railfeed/actions/workflows/tests.yml)

Live UK train departures for a station, from the free [RailFeed API](https://railfeed.co.uk/docs)
(built on Network Rail TRUST/Darwin feeds).

## Install

### HACS (recommended)

1. In Home Assistant open **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/torstenknoefel/ha-railfeed` with category **Integration**.
3. Search for **RailFeed**, download it, and restart Home Assistant.

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=torstenknoefel&repository=ha-railfeed&category=integration)

### Manual

Copy `custom_components/railfeed` into your HA config folder's `custom_components/` directory and restart.

### Set up

1. Create a free account at <https://railfeed.co.uk>, then copy your key from
   <https://railfeed.co.uk/api-keys>.
2. **Settings → Devices & services → Add integration → RailFeed**. Enter the key and the
   three-letter station (CRS) code, e.g. `LDS` (Leeds), `KGX` (King's Cross), `WIM` (Wimbledon).
   Optionally add a **calling at** station (see below).

Add the integration again for each extra station, or for the same station with a different
**calling at** station (one entry per station + destination pair; the same key can be reused).
For example `LDS` calling at `YRK` and `LDS` calling at `MAN` give two separate devices,
"Leeds to York" and "Leeds to Manchester Piccadilly", each with its own sensors.

## Entities (per station)

| Entity | Meaning |
|---|---|
| Next departure | Timestamp of the next running train (expected time). Attributes carry full details + a `departures` list |
| Next destination / platform / delay / status | Details of that next train (`on_time`, `delayed`, `cancelled`) |
| Delayed services / Cancelled services | Counts across the departures kept on the board |

The `departures` attribute on **Next departure** is a list of dicts with `destination`, `scheduled_time`,
`expected_time`, `platform`, `status`, `delay_minutes`, `operator`, `cancel_reason`, `late_reason`, `coaches`, etc.
It is excluded from the recorder database.

## Options (cog icon on the integration)

- **Update interval**: default 60 s, minimum 30 s (RailFeed asks for no more than one poll per 30 s;
  limit is 60 requests/min per key).
- **Departures to keep** (default 10), **look-ahead window** (default 2 h).
- **Passenger trains only** (default on): hides freight, empty stock and charters.
- **Only trains calling at this station**: optional CRS code of any station on the train's route, e.g. `YRK`.
  Chosen when you add the entry (it is what makes the entry unique); to change it, add a new entry and remove the old one.
  (Entries created with v0.2.x keep it here in the options.)
  Only trains that stop there *after* your station are listed, whether or not it is their final destination.
  Each train also gets `calling_at_arrival` (advertised arrival time there) and `journey_minutes` attributes.
  This costs one extra API request per 15 minutes per entry (the answer is cached). Each entry also polls
  the live board, and the limit is 60 requests/min per key, so a handful of entries is fine.
- **Show route as "via" these stations**: optional, up to 5 comma-separated CRS codes, e.g. `GNW, LEW`.
  Use it when the same destination is reached by different routes (for example London Cannon Street via
  Greenwich *or* via Lewisham). Every train that calls at one of these stations gets it appended to its
  destination: `London Cannon Street via Greenwich`. The rules are the same for every route:
  a train is labelled with each via station it stops at after your station, in route order
  (`via Greenwich and Deptford`); a train that only runs through the station is not labelled; and a train
  that *ends* at a via station is not labelled with it. Pick stations that every train on that route stops at.
  The label is in the `destination` attribute and in the *Next destination* sensor; the plain name is kept in
  `destination_name` and the list of stations in `via`. Each via station costs one cached API request per
  15 minutes per entry. If that lookup fails, the board still works, just without the label.
- **Destination filter**: optional CRS codes of the train's *final* destination, e.g. `KGX, EDB`.
  Can be combined with the option above.

## Dashboard card

```yaml
type: markdown
title: Leeds departures
content: |
  | Time | Destination | Plat | Status |
  |---|---|---|---|
  {% for d in state_attr('sensor.leeds_next_departure', 'departures') or [] -%}
  | {{ d.scheduled_time }} | {{ d.destination }} | {{ d.platform or '-' }} | {{ 'Exp ' ~ d.expected_time if d.status == 'delayed' else ('Cancelled' if d.status == 'cancelled' else 'On time') }} |
  {% endfor %}
```

Adjust the entity id to match yours (it follows the station's device name).

## Tutorial: a departures board with flex-table-card

This builds a board for one route that lists each train's **destination (with its "via" route)**,
scheduled time, estimated arrival, status and delay, shows **cancelled trains in red**, and only appears
when there is something to show. The example is a south-east London route where Cannon Street trains run
either via Greenwich or via Lewisham; replace the stations with your own.

### 1. Install flex-table-card

It is a separate dashboard card. In HACS open **Frontend**, search for **flex-table-card**
(`custom-cards/flex-table-card`), download it and reload the browser.

### 2. Set up the route and the "via" stations

1. Add the integration with your station (example: `DFD`, Dartford) and **Only trains calling at** `CST`
   (London Cannon Street). That gives every train a `calling_at_arrival` time, which the *Est. arrival*
   column needs. Without it that column shows a dash.
2. Open the integration's **Configure** (cog) and set **Show route as 'via' these stations** to `GNW, LEW`
   (Greenwich, Lewisham). Trains to Cannon Street now read *London Cannon Street via Greenwich* or
   *London Cannon Street via Lewisham*. Any other pair of routes works the same way: add a station that
   only one of the routes stops at.

### 3. Find your entity ids

Open **Settings → Devices & services → RailFeed**, pick the device and note its entity ids.
They follow the device name; for the example they would be:

| Entity | Used for |
|---|---|
| `sensor.dartford_to_london_cannon_street_next_departure` | holds the `departures` list the table is built from |
| `sensor.dartford_to_london_cannon_street_next_status` | tells the card whether a train is running |
| `sensor.dartford_to_london_cannon_street_cancelled_services` | tells the card whether any train is cancelled |

If yours differ, replace them in the YAML below.

### 4. Add the card

On your dashboard choose **Edit → Add card → Manual**, and paste:

```yaml
type: conditional
conditions:
  - condition: or
    conditions:
      - condition: state
        entity: sensor.dartford_to_london_cannon_street_next_status
        state_not:
          - unknown
          - unavailable
      - condition: numeric_state
        entity: sensor.dartford_to_london_cannon_street_cancelled_services
        above: 0
card:
  type: custom:flex-table-card
  title: Dartford → London Cannon Street
  entities:
    include: sensor.dartford_to_london_cannon_street_next_departure
  columns:
    - name: Destination
      data: departures
      modify: |-
        (v => x.status == 'cancelled' ? '<span style="color:red">' + v + '</span>' : v)(x.destination)
    - name: Scheduled
      data: departures
      modify: |-
        (v => x.status == 'cancelled' ? '<span style="color:red">' + v + '</span>' : v)(x.scheduled_time)
    - name: Est. arrival
      data: departures
      modify: |-
        (v => x.status == 'cancelled' ? '<span style="color:red">' + v + '</span>' : v)(
          x.status == 'cancelled' || !x.calling_at_arrival ? '–' : (() => {
            const [h, m] = x.calling_at_arrival.split(':').map(Number);
            const t = h * 60 + m + x.delay_minutes;
            return String(Math.floor(t / 60) % 24).padStart(2, '0') + ':' + String(t % 60).padStart(2, '0');
          })())
    - name: Status
      data: departures
      modify: |-
        (v => x.status == 'cancelled' ? '<span style="color:red">' + v + '</span>' : v)(
          x.status == 'cancelled' ? 'Cancelled' : x.status == 'delayed' ? 'Delayed' : 'On time')
    - name: Delay
      data: departures
      modify: |-
        (v => x.status == 'cancelled' ? '<span style="color:red">' + v + '</span>' : v)(
          x.status != 'cancelled' && x.delay_minutes ? x.delay_minutes + ' min' : '–')
```

How it works:

- **flex-table-card** reads the `departures` list from the sensor and builds one row per train. Each column
  has `data: departures`, and its `modify` expression gets the train as `x` and returns the cell's HTML.
- **Destination** is `x.destination`, which already contains the "via" text. The plain name is `x.destination_name`
  if you want it without the route.
- **Red for cancelled trains:** every column wraps its value in `<span style="color:red">` when
  `x.status == 'cancelled'`. Change the colour name or use a hex code such as `#d32f2f`.
- **Est. arrival** is the advertised arrival at the "calling at" station plus the train's current delay
  (`calling_at_arrival` + `delay_minutes`), wrapped past midnight. It is an estimate, as trains can make up
  or lose time. It is a dash for cancelled trains.
- **The conditional card** wraps the table and shows it only when at least one condition holds (`or`):
  the next train has a real status, or at least one service is cancelled. The second condition matters
  because when every listed train is cancelled there is no "next train", yet you still want to see them.
- The table length follows **Departures to keep** and **Look-ahead window** in the integration's options.

A board might look like this (cancelled row shown in red on the dashboard):

| Destination | Scheduled | Est. arrival | Status | Delay |
|---|---|---|---|---|
| London Cannon Street via Greenwich | 17:55 | 19:29 | Delayed | 8 min |
| London Cannon Street via Lewisham (red) | 18:00 (red) | – (red) | Cancelled (red) | – (red) |
| London Cannon Street via Greenwich | 18:25 | 19:51 | On time | – |

### 5. Optional: a message when there are no trains

Add a second conditional card beneath the first. It appears only when there is no running train
**and** nothing cancelled, so the two cards never show together:

```yaml
type: conditional
conditions:
  - condition: state
    entity: sensor.dartford_to_london_cannon_street_next_status
    state: unknown
  - condition: numeric_state
    entity: sensor.dartford_to_london_cannon_street_cancelled_services
    below: 1
card:
  type: markdown
  content: No trains to London Cannon Street in the look-ahead window.
```

With a list of `conditions`, *all* of them must hold; the first card needed `or` to show on *either*.

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
    entity_id: sensor.leeds_next_status
    to: [delayed, cancelled]
condition:
  - condition: time
    after: "07:00:00"
    before: "09:00:00"
action:
  - service: notify.notify
    data:
      message: >
        {{ state_attr('sensor.leeds_next_departure','scheduled_time') }} to
        {{ states('sensor.leeds_next_destination') }} is {{ states('sensor.leeds_next_status') }}
        ({{ states('sensor.leeds_next_delay') }} min).
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

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-orange.svg
[hacs-url]: https://hacs.xyz
