# Snoozefest Handoff (2026-03-31)

## Current Status

- Dashboard assets were moved from repo root to `dashboard/`.
- Voice automation YAML files were moved from repo root to `voice/`.
- Timer add-button behavior in `dashboard/ha_dashboard_timers_auto_list_card.yaml` was fixed to:
  - resolve manager prefix from discovered entities,
  - only open detail after confirmed timer creation.

## Folder Layout (Current)

### Core app

- `src/snoozefest/`
- `config.example.json`
- `DEPLOYMENT.md`
- `MIGRATION.md`

### Dashboard assets

- `dashboard/ha_dashboard_alarms_simple_auto_list_card.yaml`
- `dashboard/ha_dashboard_timers_auto_list_card.yaml`
- `dashboard/ha_dashboard_alarm_detail_popup_card.yaml`
- `dashboard/ha_dashboard_timer_detail_popup_card.yaml`
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
   - `/local/dashboard/time_picker_custom.js`
   - `/local/dashboard/input_text.js`
4. Re-import dashboard YAML from `dashboard/` paths.
5. Re-import voice automations from `voice/` paths.
6. Restart Snoozefest daemon/add-on.
7. Verify:
   - timer add button creates and opens new timer,
   - alarm/timer detail cards render,
   - voice automations trigger correctly.

## Known Notes

- `dashboard/ha_dashboard_alarm_detail_popup_card.yaml` still has the known popup-prefix-variable limitation documented in `.github/copilot-instructions.md`.
- `TIMER_UI_ROADMAP.md` remains the source for future JS-card consolidation decisions.