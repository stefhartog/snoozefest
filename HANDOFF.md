# Snoozefest Handoff (2026-03-31)

## Current Status

- Dashboard assets were moved from repo root to `dashboard/`.
- Voice automation YAML files were moved from repo root to `voice/`.
- Dashboard prefix handling was simplified to a default `snoozefest` path with optional explicit override, removing the old helper-driven env lookup from active dashboard flows.
- `dashboard/snoozefest_entity_card.js` now exists as the refactored card name and is interchangeable with the legacy time-picker card in current dashboard usage.

## Folder Layout (Current)

### Core app

- `src/snoozefest/`
- `config.example.json`
- `DEPLOYMENT.md`
- `MIGRATION.md`

### Dashboard assets

- `dashboard/alarm_list_card.yaml`
- `dashboard/timer_list_card.yaml`
- `dashboard/alarm_detail_card.yaml`
- `dashboard/timer_detail_card.yaml`
- `dashboard/snoozefest_entity_card.js`
- `dashboard/time_picker_custom.js`
- `dashboard/input_text.js`

### Voice automations

- `voice/ha_voice_master_automation.yaml`
- `voice/ha_voice_ringing_announce_automation.yaml`
- `voice/ha_voice_router.yaml`

### Add-on source (workspace sibling)

- `../ha-addons/snoozefest/`

## HA Migration Checklist

1. Commit and push current branch.
2. Pull this branch on the HA-side working copy.
3. Update Lovelace resources:
   - `/local/dashboard/snoozefest_entity_card.js`
   - `/local/dashboard/time_picker_custom.js`
   - `/local/dashboard/input_text.js`
4. Re-import dashboard YAML from `dashboard/` paths.
5. Re-import voice automations from `voice/` paths.
6. Restart Snoozefest daemon/add-on.
7. Verify:
   - both `custom:snoozefest-entity-card` and legacy `custom:snoozefest-time-picker-card` resources load,
   - timer add button creates and opens new timer,
   - alarm/timer detail cards render,
   - voice automations trigger correctly.

## Known Notes

- `dashboard/alarm_detail_card.yaml` still has the known popup-prefix-variable limitation documented in `.github/copilot-instructions.md`.
- `dashboard/time_picker_custom.js` is still retained for compatibility while dashboards migrate to `dashboard/snoozefest_entity_card.js`.
- `TIMER_UI_ROADMAP.md` remains the source for future JS-card consolidation decisions.