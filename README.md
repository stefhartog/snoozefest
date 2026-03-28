# snoozefest

Local alarm and timer service with JSON persistence and Home Assistant MQTT discovery.

The current control model is entity-first:

- one Home Assistant MQTT manager device (`Snoozefest`)
- one device per alarm
- one device per timer

No dashboard YAML or HA script glue is required for normal operation.

## Quick start

```bash
cd snoozefest
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -e .
```

Run the daemon:

```bash
snoozefest --config config.json run
```

## Deployment

### Local development (Windows/Mac/Linux)

Use the quick start setup above for testing and local development. Creates a dev instance with `snoozefest_dev` MQTT namespace.

### Production (Home Assistant Add-on)

For persistent deployment on Home Assistant:

1. Navigate to `addon/` folder
2. Follow [addon/README.md](addon/README.md) for installation
3. See [MIGRATION.md](MIGRATION.md) for importing dev state to production

When deployed as an add-on, Snoozefest publishes to the `snoozefest` MQTT namespace (distinct from local dev instance).

Both dev and production instances can coexist without conflict.

## Operating model

- Fully local scheduler loop with atomic JSON writes.
- MQTT command + state bridge.
- Discovery payloads are retained and device-scoped.
- Runtime state topics update independently from discovery.

## Manager actions

The Snoozefest manager device exposes:

- Add Alarm
- Add Timer
- Purge All Alarms and Timers

All manager actions are Snoozefest-scoped and do not perform broker-wide cleanup.

## Core MQTT command topics

Prefix comes from `mqtt_topic_prefix` in config (default: `snoozefest`).

- <prefix>/cmd/purge_all
- <prefix>/cmd/alarm/new
- <prefix>/cmd/alarm/set
- <prefix>/cmd/alarm/update
- <prefix>/cmd/alarm/remove
- <prefix>/cmd/alarm/snooze
- <prefix>/cmd/alarm/dismiss
- <prefix>/cmd/timer/new
- <prefix>/cmd/timer/set
- <prefix>/cmd/timer/update
- <prefix>/cmd/timer/cancel
- <prefix>/cmd/timer/remove
- <prefix>/cmd/timer/snooze
- <prefix>/cmd/timer/dismiss
- <prefix>/cmd/state/request

Per-entity set topics are also used by HA discovery entities, for example:

- <prefix>/cmd/alarm/<id>/enabled/set
- <prefix>/cmd/alarm/<id>/time/set
- <prefix>/cmd/alarm/<id>/label/set
- <prefix>/cmd/alarm/<id>/weekday/<0-6>/set
- <prefix>/cmd/timer/<id>/label/set
- <prefix>/cmd/timer/<id>/duration/set

## Core state topics

- <prefix>/state/online (retained true/false)
- <prefix>/state/alarms (retained JSON list)
- <prefix>/state/timers (retained JSON list)
- <prefix>/state/active_alarm (retained JSON)
- <prefix>/state/next_alarm (retained JSON or null)
- <prefix>/state/ringing_timer_count (retained integer)
- <prefix>/state/command_result (event, not retained)
- <prefix>/state/error (event, not retained)
- <prefix>/state/heartbeat (event, not retained)
- <prefix>/state/alarm_triggered (event, not retained)
- <prefix>/state/timer_finished (event, not retained)

## Behavior highlights

- Unified alarm model:
  - weekdays omitted on update keeps current kind
  - weekdays empty means one-off
  - weekdays non-empty means recurring
- New alarms are created disabled by default.
- New timers are created in dismissed state by default.
- Purge All removes only Snoozefest alarms/timers from scheduler state.
- Timer discovery payloads are not republished every tick; runtime state updates are.
- Recurring alarms do not catch up missed triggers after downtime.
- IDs are compact numeric strings with max 25 alarms and 25 timers.

## Config

Use `config.example.json` as a template.

| Key | Default | Description |
|---|---|---|
| mqtt_host | required | Broker hostname or IP |
| mqtt_port | 1883 | Broker port |
| mqtt_username | "" | MQTT username |
| mqtt_password | "" | MQTT password |
| mqtt_topic_prefix | snoozefest | Root MQTT topic |
| mqtt_client_id | snoozefest | MQTT client ID |
| homeassistant_discovery_prefix | homeassistant | HA MQTT discovery prefix |
| timezone | UTC | IANA timezone |
| data_file | snoozefest_data.json | Persistent JSON state path |
| tick_seconds | 1 | Scheduler loop interval |
| default_snooze_minutes | 10 | Default alarm snooze minutes |

## CLI helpers

Useful local commands:

```bash
snoozefest --config config.json run
snoozefest --config config.json add-oneoff --time 07:30 --label Wake
snoozefest --config config.json add-recurring --time 07:00 --weekdays 0,1,2,3,4 --label Work
snoozefest --config config.json list-alarms
snoozefest --config config.json show-next
```

## Home Assistant workflow

1. Use manager buttons to create alarms and timers.
2. Configure each alarm/timer from its own device entities.
3. Use per-device `Remove` to permanently remove that object.
4. Use manager `Purge All` only when you intentionally want to clear all Snoozefest alarms and timers.

## Project layout

```text
src/snoozefest/
  __main__.py
  cli.py
  config.py
  daemon.py
  models.py
  mqtt_client.py
  scheduler.py
  store.py
```
