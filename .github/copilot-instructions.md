# Copilot Instructions For Snoozefest

This project is a local-first scheduler with Home Assistant MQTT discovery.

## Primary Goals

- Keep behavior deterministic and safe for home automation.
- Prefer MQTT entity-first flows over dashboard/script glue.
- Avoid broad MQTT cleanup actions that can affect other devices.

## Coding Preferences

- Keep changes minimal and localized.
- Preserve current naming and topic conventions.
- Prefer explicit validation and clear error messages on command handlers.
- Favor atomic scheduler operations over multi-step daemon workarounds.

## Reliability Rules

- Discovery payloads should publish on topology/schema changes, not every tick.
- Runtime state topics may update every tick where needed.
- Any new create flows should support safe defaults in one atomic call.
- Batch destructive operations where possible with one save and one state callback.

## Security Rules

- Never commit real credentials in examples or scripts.
- Use placeholders in tracked config files.
- Use environment variables or runtime parameters for secrets.

## Home Assistant Conventions

- One manager device (Snoozefest).
- One device per alarm and one per timer.
- Device names should stay tidy and prefixed:
  - Snoozefest Alarm - <Label>
  - Snoozefest Timer - <Label>

## Documentation Rules

- Keep README aligned with actual command topics and behavior.
- Remove references to deleted legacy dashboard/script files.
- Mention entity-first management as the default path.
- Keep voice automation docs/scripts aligned with current MQTT topic-prefix variable usage.
- Document `command_result.request_id` as optional when request correlation is implemented.
- Keep add-on docs aligned with Dockerfile source behavior (GitHub clone at build, cache-bust rules, and commit SHA visibility in logs).

## Validation Before Finish

- Run compile check:
  - python -m compileall src
- Restart daemon and confirm logs show:
  - Snoozefest daemon running
  - MQTT connected

## Codebase Notes

### humanize.py
- `duration_to_speech(total_seconds)` — renders "2 hours 30 minutes", "45 seconds", "now", or "" for None/disabled
- `remaining_to_day_phrase(total_seconds, now=None)` — returns "today", "tomorrow", or weekday name (e.g. "Tuesday")
  - Pass `now=datetime.now(self._tz)` in the daemon for timezone-aware results

### Alarm and timer sensor naming convention
Alarm per-device sensors use a numbered-prefix naming scheme (controls ordering in HA):
- `07a` Status — entity suffix `_status`
- `07b` Remaining Friendly — entity suffix `_remaining_friendly`, uses `duration_to_speech`
- `07c` Next Day — entity suffix `_next_day`, uses `remaining_to_day_phrase`

Timer sensors follow a similar pattern (`09a`, `09b`, etc.).

### Dashboard cards (root YAML files)
- `ha_dashboard_alarms_auto_list_card.yaml` — flex-table-card listing all alarms
- `ha_dashboard_timers_auto_list_card.yaml` — flex-table-card listing all timers
  (has a commented-out `snoozefest_dev` include line as a manual dev/prod toggle pattern)
- `ha_dashboard_alarm_detail_popup_card.yaml` — single alarm detail popup card
  - Uses `custom:config-template-card`; `vars[0]` holds the alarm ID string
  - All entity IDs are hard-coded to the `snoozefest_*` prefix
  - **KNOWN BROKEN**: Using `vars[1]` as an MQTT prefix variable breaks this card when
    invoked from a popup wrapper (browser_mod etc.). Do not retry this approach.
  - **OPEN TASK**: Implement a working dev/prod MQTT prefix switch for this card.
    Preferred alternatives: comment-based toggle (like the timer list card) or reading
    from a `input_text.snoozefest_env` HA entity at runtime.
