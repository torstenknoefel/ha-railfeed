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
- Platforms the operator has asked to keep off public screens are hidden.
- Data is attributed to RailFeed; not affiliated with National Rail.

## Development

```bash
pip install pytest
pytest          # parser tests, no Home Assistant needed
```

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-orange.svg
[hacs-url]: https://hacs.xyz
