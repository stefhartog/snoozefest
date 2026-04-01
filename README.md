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

Use the quick start setup above for testing and local development. The MQTT namespace comes from your chosen config file. In this workspace, `config.json` is commonly used for a `snoozefest_dev` test instance, while `config.example.json` shows the default `snoozefest` prefix.

### Production (Home Assistant Add-on)

For persistent deployment on Home Assistant:

1. Navigate to `../ha-addons/snoozefest/` folder
2. Follow [../ha-addons/snoozefest/README.md](../ha-addons/snoozefest/README.md) for installation
3. See [MIGRATION.md](MIGRATION.md) for importing dev state to production

When deployed as an add-on, Snoozefest typically publishes to the `snoozefest` MQTT namespace.

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
- <prefix>/cmd/timer/add_time
- <prefix>/cmd/timer/snooze
- <prefix>/cmd/timer/pause
- <prefix>/cmd/timer/resume
- <prefix>/cmd/timer/activate
- <prefix>/cmd/timer/reset
- <prefix>/cmd/timer/dismiss
- <prefix>/cmd/settings/timer_add_seconds/set
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
- <prefix>/state/alarms_glance (retained summary string)
- <prefix>/state/timers_glance (retained summary string)
- <prefix>/state/active_alarm (deprecated, published empty for cleanup)
- <prefix>/state/next_alarm (retained JSON or null)
- <prefix>/state/ringing_alarm_count (retained integer)
- <prefix>/state/ringing_timer_count (retained integer)
- <prefix>/state/command_result (event, not retained; includes optional request_id)
- <prefix>/state/error (event, not retained)
- <prefix>/state/heartbeat (event, not retained)
- <prefix>/state/alarm_triggered (event, not retained)
- <prefix>/state/timer_finished (event, not retained)

## Behavior highlights

- Unified alarm model:
  - weekdays omitted on update keeps current kind
  - weekdays empty means one-off
  - weekdays non-empty means recurring
- Alarm recurring is derived from selected weekdays and is no longer intended as a separate manual UI control.
- New alarms are created enabled by default.
- New timers are created inactive by default.
- New alarm and timer labels default to empty values.
- Purge All removes only Snoozefest alarms/timers from scheduler state.
- Timer discovery payloads are not republished every tick; runtime state updates are.
- Ringing alarms and timers auto-dismiss after 5 minutes.
- Timers support `inactive`, `active`, `paused`, and `ringing` states.
- Timers support `reset`, which restores the configured duration without starting the timer.
- Recurring alarms do not catch up missed triggers after downtime by default.
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
| timer_add_seconds | 60 | Default seconds added by timer Add Time action |
| alarm_trigger_grace_seconds | 120 | Optional extra seconds added after the scheduled minute window (`HH:MM:00..HH:MM:59`); `0` keeps minute-only triggering |

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
dashboard/
voice/
src/snoozefest/
  __main__.py
  cli.py
  config.py
  daemon.py
  humanize.py
  models.py
  mqtt_client.py
  scheduler.py
  store.py
```

## Alarm sensors per device

Each alarm device publishes the following sensors (prefix controls ordering in HA):

| Sensor | Entity suffix | Description |
|---|---|---|
| `07a` Status | `_status` | Current alarm state (idle, ringing, snoozed, etc.) |
| `07b` Remaining Friendly | `_remaining_friendly` | Human-readable time remaining (e.g. "2 hours 30 minutes") |
| `07c` Next Day | `_next_day` | Day the alarm fires: "today", "tomorrow", or weekday name |

## Dashboard cards

Dashboard YAML files and the custom time picker card are now grouped under `dashboard/`:

| File | Purpose |
|---|---|
| `dashboard/alarm_list_card.yaml` | Auto-list of all alarm entities |
| `dashboard/timer_list_card.yaml` | Auto-list of all timer entities rendered with the Snoozefest custom entity card rows |
| `dashboard/alarm_detail_card.yaml` | Single-alarm detail popup; set alarm ID in `variables[0]` |
| `dashboard/timer_detail_card.yaml` | Single-timer detail popup; reads selected timer ID from `input_text.snoozefest_timer_id` |
| `dashboard/snoozefest_entity_card.js` | Current custom Lovelace entity card for alarm/timer row and detail time UI |
| `dashboard/time_picker_custom.js` | Legacy compatible custom Lovelace card kept for migration/backward compatibility |
| `dashboard/input_text.js` | Custom Lovelace multiline text input card |

## Voice automations

Voice-related Home Assistant automations are grouped under `voice/`:

| File | Purpose |
|---|---|
| `voice/ha_voice_master_automation.yaml` | Conversation routing automation for voice alarm/timer intents |
| `voice/ha_voice_ringing_announce_automation.yaml` | Satellite announcement automation for ringing alarms/timers |
| `voice/ha_voice_router.yaml` | Script-style MQTT command router used by voice flows |

For future UI consolidation, helper-removal planning, and the longer-term move toward a fully Snoozefest-owned detail card stack, see `TIMER_UI_ROADMAP.md`.
