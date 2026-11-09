# RailFeed attribute reference

[← Back to the README](../README.md)

Every RailFeed sensor carries attributes you can read in templates, automations and dashboard cards with
`state_attr('sensor.your_sensor', 'attribute_name')` (or `states.sensor.your_sensor.attributes.attribute_name`).
Entity ids follow your device name, for example `sensor.belvedere_to_abbey_wood_next_departure`; use your own.

- [Sensors at a glance](#sensors-at-a-glance)
- [Attributes on every sensor](#attributes-on-every-sensor)
  - [Configuration attributes (`config_*`)](#configuration-attributes-config_)
- [Attributes of the Next departure sensor](#attributes-of-the-next-departure-sensor)
  - [Station attributes](#station-attributes)
  - [Next train attributes](#next-train-attributes)
  - [The `departures` list](#the-departures-list)
- [Examples](#examples)

## Sensors at a glance

| Sensor | State | Extra attributes |
|---|---|---|
| **Next departure** | Expected departure time of the next running train (timestamp) | [Station](#station-attributes), [next train](#next-train-attributes), [`departures`](#the-departures-list), [`config_*`](#configuration-attributes-config_) |
| **Next destination** | Destination of the next running train, with its route: `London Cannon Street via Greenwich` | [`config_*`](#configuration-attributes-config_) |
| **Next platform** | Platform of the next running train | [`config_*`](#configuration-attributes-config_) |
| **Next delay** | Minutes the next running train is late (`0` if on time), unit `min` | [`config_*`](#configuration-attributes-config_) |
| **Next status** | `on_time`, `delayed` or `cancelled` for the next running train | [`config_*`](#configuration-attributes-config_) |
| **Delayed services** | How many of the kept departures are delayed | [`config_*`](#configuration-attributes-config_) |
| **Cancelled services** | How many of the kept departures are cancelled | [`config_*`](#configuration-attributes-config_) |

"Next running train" means the first departure on the board that is not cancelled. When there is none, the
state of the four *Next …* sensors is `unknown`, and the next-train attributes are missing, but the
[`departures`](#the-departures-list) list and all `config_*` attributes are still there.

## Attributes on every sensor

| Attribute | Type | Meaning |
|---|---|---|
| `attribution` | text | Data source credit (RailFeed, built on Network Rail and Darwin feeds). Added by Home Assistant |
| `config_*` | various | The setup's configuration, see below |

Home Assistant also adds its usual `friendly_name`, `device_class`, `unit_of_measurement` and `state_class`
attributes where they apply.

### Configuration attributes (`config_*`)

These show how the setup is configured, so a template or card can adapt to it without you repeating the
setting by hand. They are the same on all seven sensors of a setup, and they follow the options: change an option,
the integration reloads, and the attributes update.

| Attribute | Type | Example | Matches the setting | Meaning |
|---|---|---|---|---|
| `config_station` | text | `BVD` | Station | Three-letter (CRS) code of the station the board is for |
| `config_calling_at` | text or none | `ABW` | Only trains calling at | CRS code of the "calling at" station. `none` when not set |
| `config_via` | list of text | `["GNW", "LEW"]` | Show route as "via" these stations | CRS codes used to label routes, sorted alphabetically. Empty list when not set |
| `config_destinations` | list of text | `["KGX", "EDB"]` | Only trains to these destinations | CRS codes of the final destinations that are allowed, sorted alphabetically. Empty list means all destinations |
| `config_passenger_only` | true / false | `true` | Passenger trains only | Whether freight, empty stock and charters are hidden |
| `config_max_departures` | number | `10` | Departures to keep | How many departures are kept on the board (the most the `departures` list can hold) |
| `config_look_ahead_hours` | number | `2` | Look-ahead window (hours) | How far ahead the board looks, in hours |
| `config_update_interval_seconds` | number | `60` | Update interval (seconds) | How often the data is refreshed, in seconds |

Notes:

- Values are the ones in effect, so a setting you never changed shows its default (for example `2` hours).
- `config_calling_at` is also available as `calling_at` on the Next departure sensor (see below). It is the same value.
  `config_calling_at` is on every sensor.

## Attributes of the Next departure sensor

This sensor carries the full details. Its attributes come in three groups.

### Station attributes

| Attribute | Type | Example | Meaning |
|---|---|---|---|
| `station` | text | `Belvedere` | Name of the station the board is for |
| `calling_at` | text | `ABW` | CRS code of the "calling at" station. Only present when one is set |

### Next train attributes

These describe the next running train and are missing when there is none. They are the same fields as in each
entry of the [`departures`](#the-departures-list) list, so the first running entry of that list equals them.

| Attribute | Type | Example | Meaning |
|---|---|---|---|
| `destination` | text | `London Cannon Street via Greenwich` | Final destination, with the route appended when a "via" station applies |
| `destination_name` | text | `London Cannon Street` | Final destination only, without the route |
| `via` | list of text | `["Greenwich"]` | Names of the configured "via" stations this train calls at, in route order. Empty list if none |
| `destination_crs` | text | `CST` | CRS code of the final destination |
| `origin` | text | `Gillingham (Kent)` | Where the train started its journey |
| `operator` | text | `Southeastern` | Train operating company |
| `headcode` | text | `2N46` | Four-character train identifier. The first digit is the train class (`1` express passenger, `2` ordinary passenger, `9` special, Thameslink and Eurostar, and so on) |
| `scheduled_time` | text | `17:55` | Timetabled departure time, `HH:MM`, UK time |
| `expected_time` | text | `18:03` | Expected (or actual, once departed) departure time, `HH:MM`, UK time. Equals `scheduled_time` for an on-time or cancelled train |
| `scheduled` | text | `2026-11-09T17:55:00+00:00` | Timetabled departure as a full ISO 8601 date and time with offset |
| `expected` | text | `2026-11-09T18:03:00+00:00` | Expected departure as a full ISO 8601 date and time with offset. Use it for calculations such as "minutes until" |
| `platform` | text or none | `2` | Platform. `none` when unknown, or when the operator asked for platforms to stay off public screens |
| `platform_confirmed` | true / false | `true` | Whether the live platform has been confirmed by the operator |
| `platform_changed` | true / false | `false` | `true` when the live platform differs from the booked one |
| `status` | text | `delayed` | `on_time`, `delayed` (1 minute or more late) or `cancelled` |
| `delay_minutes` | number | `8` | Minutes late. `0` when on time or cancelled |
| `cancel_reason` | text or none | `a fault with the signalling` | Why the train is cancelled. Only set for cancelled trains |
| `late_reason` | text or none | `a points failure` | Why the train is late. Only set while the train is delayed |
| `coaches` | number or none | `8` | Number of coaches, when the operator reports the formation |
| `calling_at_arrival` | text or none | `18:07` | Advertised arrival time at the "calling at" station, `HH:MM`. Only set when "calling at" is configured |
| `journey_minutes` | number or none | `12` | Scheduled journey time to the "calling at" station, in minutes. Only set when "calling at" is configured |
| `service_uid` | text | `W12345` | RailFeed/Network Rail schedule identifier of the train |

### The `departures` list

`departures` is a list with one entry per kept departure, soonest first, **including cancelled trains** (the
Next sensors skip those, the list does not). It holds at most `config_max_departures` entries and covers the
look-ahead window. Each entry has exactly the fields listed under [Next train attributes](#next-train-attributes).

The list can be large and changes every update, so it is **not stored in the recorder database**: you can use it
in templates and cards, but not in history graphs or long-term statistics.

## Examples

How many hours does the board look ahead?

```jinja
{{ state_attr('sensor.belvedere_to_abbey_wood_next_status', 'config_look_ahead_hours') }}
```

Is this setup filtering by a calling-at station, and which?

```jinja
{% set c = state_attr('sensor.belvedere_to_abbey_wood_next_status', 'config_calling_at') %}
{{ 'Only trains calling at ' ~ c if c else 'All trains' }}
```

Minutes until the next running train leaves:

```jinja
{% set e = state_attr('sensor.belvedere_to_abbey_wood_next_departure', 'expected') %}
{{ ((as_datetime(e) - now()).total_seconds() / 60) | round(0) if e else 'none' }}
```

Number of cancelled trains in the `departures` list, counted yourself:

```jinja
{{ state_attr('sensor.belvedere_to_abbey_wood_next_departure', 'departures')
   | selectattr('status', 'eq', 'cancelled') | list | count }}
```

A message that adapts to the look-ahead window is in the README's
[no-trains card](../README.md#5-optional-a-message-when-there-are-no-trains).
