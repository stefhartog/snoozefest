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
