# snoozefest

Standalone local alarm scheduler with JSON persistence and 2-way MQTT control.

## Design goals

- Fully local and deterministic
- JSON persistence with atomic writes
- MQTT bidirectional control for Home Assistant front-end
- Recurring alarms remain enabled after dismiss

## Quick start

```bash
cd snoozefest
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

Run daemon mode:

```bash
snoozefest --config config.example.json run
```

Use local CLI commands for testing (daemon not required):

```bash
snoozefest --config config.example.json add-oneoff --time 07:30 --label Wake
snoozefest --config config.example.json add-recurring --time 07:00 --weekdays 0,1,2,3,4 --label Work
snoozefest --config config.example.json list-alarms
snoozefest --config config.example.json show-next
```

## MQTT topics

Prefix comes from `mqtt_topic_prefix` in config (default `snoozefest`).

Commands to publish to:

- `<prefix>/cmd/alarm/set`
- `<prefix>/cmd/alarm/new`
- `<prefix>/cmd/alarm/update`
- `<prefix>/cmd/alarm/remove`
- `<prefix>/cmd/alarm/snooze`
- `<prefix>/cmd/alarm/dismiss`
- `<prefix>/cmd/timer/set`
- `<prefix>/cmd/timer/update`
- `<prefix>/cmd/timer/cancel`
- `<prefix>/cmd/timer/remove`
- `<prefix>/cmd/timer/snooze`
- `<prefix>/cmd/timer/dismiss`
- `<prefix>/cmd/state/request`

State topics published by service:

- `<prefix>/state/online` (retained, `true`/`false`)
- `<prefix>/state/next_alarm` (retained JSON object or `null`)
- `<prefix>/state/alarms` (retained JSON list)
- `<prefix>/state/timers` (retained JSON list)
- `<prefix>/state/active_alarm` (retained status + ringing list)
- `<prefix>/state/ringing_timer_count` (retained integer count of timers currently ringing)
- `<prefix>/state/alarm_triggered` (event list, not retained)
- `<prefix>/state/timer_finished` (event list, not retained)
- `<prefix>/state/command_result` (command ack, not retained)
- `<prefix>/state/error` (error detail, not retained)
- `<prefix>/state/heartbeat` (periodic timestamp, not retained)

Home Assistant discovery topics published by service:

- `<discovery_prefix>/switch/<prefix>_alarm_<id>/config` (retained MQTT discovery switch per alarm)
- `<discovery_prefix>/button/<prefix>_alarm_<id>_remove/config` (retained MQTT discovery remove button per alarm)
- `<discovery_prefix>/button/<prefix>_alarm_<id>_snooze/config` (retained MQTT discovery snooze button per alarm)
- `<discovery_prefix>/button/<prefix>_alarm_<id>_dismiss/config` (retained MQTT discovery dismiss button per alarm)
- `<discovery_prefix>/sensor/<prefix>_alarm_<id>_status/config` (retained MQTT discovery status sensor per alarm)
- `<discovery_prefix>/sensor/<prefix>_alarm_<id>_eta/config` (retained MQTT discovery ETA sensor per alarm)
- `<discovery_prefix>/sensor/<prefix>_timer_<id>_status/config` (retained MQTT discovery status sensor per timer)
- `<discovery_prefix>/sensor/<prefix>_timer_<id>_remaining/config` (retained MQTT discovery remaining-seconds sensor per timer)
- `<discovery_prefix>/button/<prefix>_timer_<id>_remove/config` (retained MQTT discovery remove button per timer)
- `<discovery_prefix>/button/<prefix>_timer_<id>_snooze/config` (retained MQTT discovery snooze button per timer)
- `<discovery_prefix>/button/<prefix>_timer_<id>_dismiss/config` (retained MQTT discovery dismiss button per timer)
- `<prefix>/state/alarm/<id>/enabled` (`ON`/`OFF`, retained)
- `<prefix>/state/alarm/<id>/status` (`idle`/`ringing`/`snoozed`, retained)
- `<prefix>/state/alarm/<id>/eta` (friendly relative countdown text, retained)
- `<prefix>/state/alarm/<id>/attributes` (JSON alarm details, retained)
- `<prefix>/state/timer/<id>/status` (`running` / `ringing` / `snoozed`, retained)
- `<prefix>/state/timer/<id>/remaining_seconds` (remaining time countdown, retained)
- `<prefix>/state/timer/<id>/attributes` (JSON timer details, retained)
- `<prefix>/cmd/alarm/<id>/enabled/set` (`ON`/`OFF` to enable or disable an alarm)

### Command payload examples

Set one-off alarm:

```json
{ "time": "07:30", "weekdays": [], "label": "Wake" }
```

Create default one-off alarm (`New Alarm`) for next minute:

```json
{}
```

Set recurring alarm:

```json
{ "time": "07:00", "weekdays": [0, 1, 2, 3, 4], "label": "Work" }
```

Update an alarm (any field except `id`):

```json
{ "id": "<uuid>", "enabled": false }
```

Unified alarm behavior:

- If `weekdays` is omitted, current kind is preserved on update.
- If `weekdays` is an empty list (`[]`), the alarm is treated as one-off.
- If `weekdays` has one or more days, the alarm is treated as recurring.
- `kind` is accepted for backward compatibility but no longer required.

Remove an alarm:

```json
{ "id": "<uuid>" }
```

Snooze currently ringing alarm:

```json
{ "minutes": 10 }
```

Dismiss currently ringing (or snoozed) alarm:

```json
{}
```

Set timer:

```json
{ "duration_seconds": 300, "label": "Tea" }
```

Update timer:

```json
{ "id": "1", "duration_seconds": 600, "label": "Egg Timer" }
```

Cancel timer:

```json
{ "id": "<uuid>" }
```

Snooze ringing timer by 1 minute:

```json
{ "id": "<id>" }
```

Dismiss ringing or snoozed timer:

```json
{ "id": "<id>" }
```

## Config

Copy and edit `config.example.json`:

| Key | Default | Description |
|---|---|---|
| `mqtt_host` | *(required)* | Broker hostname/IP |
| `mqtt_port` | `1883` | Broker port |
| `mqtt_username` | `""` | MQTT username |
| `mqtt_password` | `""` | MQTT password |
| `mqtt_topic_prefix` | `snoozefest` | Root MQTT topic |
| `mqtt_client_id` | `snoozefest` | MQTT client ID |
| `homeassistant_discovery_prefix` | `homeassistant` | MQTT discovery prefix for per-alarm HA switches |
| `timezone` | `UTC` | IANA timezone name |
| `data_file` | `snoozefest_data.json` | JSON state path |
| `tick_seconds` | `1` | Scheduler poll interval |
| `default_snooze_minutes` | `10` | Snooze duration if not specified |

## Behavior notes

- Dismissing a **one-off** alarm sets it to `enabled: false`.
- One-off alarms are configured as local time-of-day (`HH:MM`) rather than calendar date/time.
- Re-enabling a one-off alarm schedules it for the next matching time (today if still upcoming, otherwise tomorrow).
- Dismissing a **recurring** alarm clears the active ring; the alarm remains enabled and will fire again on the next matching weekday.
- Dismissing a **snoozed** alarm cancels the pending re-ring.
- Recurring alarms trigger only in their scheduled minute (no catch-up trigger if service starts later).
- Alarm IDs are numeric strings `"1"`..`"25"` across one-off + recurring alarms.
- Timer IDs are numeric strings `"1"`..`"25"`.
- Maximum counts: 25 alarms total and 25 timers total.
- Timers transition through `running` -> `ringing` -> `snoozed` and can be dismissed or removed.
- Dismissing a timer keeps it in state as `dismissed`; pressing dismiss again restarts it from its original duration.
- Timer snooze always adds 60 seconds.
- Timer remaining time is published every tick so Home Assistant can show a live 1-second countdown.
- Timer state also includes friendly duration strings such as `10 minutes`.
- Alarm ETA text is refreshed every 10 minutes (and immediately on state changes).
- JSON state is written atomically (temp-file + rename) on every mutation.
- The LWT ensures `state/online` → `false` if the process dies unexpectedly.
- Home Assistant can auto-discover each alarm as its own MQTT switch entity and toggle it on/off.

## Project layout

```
src/snoozefest/
├── __init__.py
├── __main__.py     # python -m snoozefest entry-point
├── cli.py          # click CLI (run / add-oneoff / add-recurring / list-alarms / show-next)
├── config.py       # Config dataclass loaded from JSON
├── daemon.py       # Wires Scheduler + MQTTClient into the running service
├── models.py       # AlarmOneOff, AlarmRecurring, Timer, ActiveAlarm dataclasses
├── mqtt_client.py  # paho-mqtt ≥ 2.0 wrapper
├── scheduler.py    # Tick-based alarm/timer engine with thread-safe mutations
└── store.py        # Atomic JSON persistence (AppState)
```
