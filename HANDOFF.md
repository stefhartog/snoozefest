# Snoozefest Handoff (2026-04-02)

## Current Status

- Dashboard assets were moved from repo root to `dashboard/`.
- Voice automation YAML files were moved from repo root to `voice/`.
- Dashboard prefix handling was simplified to a default `snoozefest` path with optional explicit override, removing the old helper-driven env lookup from active dashboard flows.
- `dashboard/snoozefest_entity_card.js` now exists as the refactored card name and is interchangeable with the legacy time-picker card in current dashboard usage.
- Dashboard card filenames were shortened for maintainability:
   - `dashboard/alarm_list_card.yaml`
   - `dashboard/alarm_detail_card.yaml`
   - `dashboard/timer_list_card.yaml`
   - `dashboard/timer_detail_card.yaml`
- Voice flow is now split into:
   - deterministic local sentence routing (`snoozefest_va_router_automation.yaml` + `snoozefest_va_router_script.yaml`)
   - optional LLM wrapper scripts for natural-language tool calling.
- LLM test profile proved effective for bypassing native timer-intent collisions in Assist.

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

- `voice/snoozefest_va_router_automation.yaml`
- `voice/snoozefest_va_router_script.yaml`
- `voice/snoozefest_va_ringing_automation.yaml`
- `voice/snoozefest_va_set_timer_llm_script.yaml`
- `voice/snoozefest_va_set_alarm_llm_script.yaml`
- `voice/snoozefest_va_add_time_llm_script.yaml`
- `voice/snoozefest_va_snooze_alarm_llm_script.yaml`
- `voice/snoozefest_va_dismiss_llm_script.yaml`
- `voice/snoozefest_va_llm_instructions.md`
- `voice/snoozefest_va_llm_instructions_test.md`

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
5. Re-import voice automations/scripts from `voice/` paths.
6. Restart Snoozefest daemon/add-on.
7. Verify:
   - both `custom:snoozefest-entity-card` and legacy `custom:snoozefest-time-picker-card` resources load,
   - timer add button creates and opens new timer,
   - alarm/timer detail cards render,
   - voice automations trigger correctly,
   - LLM wrapper scripts are exposed only where intended.

## Beta Tester Guidance Snapshot

Recommended rollout path for external testers:

1. Brain only first
- Install add-on and verify manager/alarm/timer entities.

2. Dashboard second
- Add `dashboard/snoozefest_entity_card.js` resource and import list/detail YAML.

3. Voice third (optional)
- Enable deterministic router automation/script first.
- Add LLM wrappers only after baseline local voice behavior is stable.

## Known Notes

- `dashboard/alarm_detail_card.yaml` still has the known popup-prefix-variable limitation documented in `.github/copilot-instructions.md`.
- `dashboard/time_picker_custom.js` is still retained for compatibility while dashboards migrate to `dashboard/snoozefest_entity_card.js`.
- `TIMER_UI_ROADMAP.md` remains the source for future JS-card consolidation decisions.
- Assist built-in timer intents can compete with Snoozefest timer phrasing; the test LLM instruction profile exists to force Snoozefest script routing when needed.