# Timer UI Roadmap (Future)

This file captures future design notes for migrating timer dashboard UX from YAML conditionals + helper entities toward a consolidated custom JS card flow.

## Goals

- Reduce rendering flicker and transient error states.
- Remove YAML duplication and brittle template interactions.
- Minimize or eliminate dashboard helper entities used only for UI glue.
- Keep actions deterministic and safe for home automation.

## Current Pain Points

- Many conditional cards mount/unmount during state changes.
- Repeated YAML blocks for similar buttons and states.
- `input_text.snoozefest_timer_id` still acts as cross-card glue in current dashboard flows.
- Brief list/detail visual instability when timers are removed/recreated.

## Current Migration State

- `dashboard/snoozefest_entity_card.js` now exists as the refactored successor to `dashboard/time_picker_custom.js`.
- The new card has been validated as an interchangeable replacement for current alarm/timer row usage.
- `dashboard/time_picker_custom.js` is still kept as a compatibility path during migration.
- `input_text.snoozefest_env` has been removed from active dashboard flows; prefix handling is now default `snoozefest` with optional explicit override.

## Target Architecture

- One JS-driven timer detail card with internal state machine.
- One JS-driven timer list card that passes selected timer context directly.
- Stable DOM: update values/styles/actions without swapping card trees.
- HA entities remain source of truth for timer domain state.

## State Model (Detail Card)

Canonical status states:

- `inactive`
- `active`
- `paused`
- `ringing`
- fallback: `unknown`/`unavailable`/missing

Derived view-model each update:

- mode: `editable` vs `readonly`
- display value source: `duration` or `remaining`
- status tint
- enabled/disabled action map
- button labels/icons per action slot

## Action Dispatch Rules

Single action dispatcher with guarded transitions:

- `inactive`
  - duration `00:00:00:00`: Start disabled, Cancel removes timer
  - duration > 0: Start enabled
- `active`: Pause enabled
- `paused`: Resume enabled
- `ringing`: Dismiss enabled
- unknown/unavailable: all command actions disabled

Command behavior:

- Resolve target entities from selected timer base.
- No-op on invalid transitions.
- Optional in-flight lock per action to prevent double firing.

## Anti-Flicker / Stability Guidelines

- Keep one persistent card instance where possible.
- Avoid large conditional wrappers for core controls.
- Coalesce rapid HA updates before render (micro-debounce).
- Treat missing entities during remove/recreate as transitional, not fatal.
- Optional short "pending removal" grace (150-300 ms) for list item fade-out.
- Prefer fallback render states over throwing card-level errors.

## Helper Entity Reduction Plan

Phase target:

- Remove `input_text.snoozefest_timer_id` from normal UI flow.
- Keep prefix handling explicit through card config/defaults; do not reintroduce helper-based env switching.

Interim compatibility:

- Keep helper support behind compatibility mode while migrating dashboards.
- Allow both old helper path and new direct-context path temporarily.

## Proposed Migration Phases

1. Stabilize current YAML + JS hybrid
- Keep rendering-safe config.
- Avoid risky inline JS interpolation patterns in YAML.

2. Build consolidated detail JS card
- Implement state model + guarded dispatcher.
- Match existing actions and visual behavior first.

3. Integrate list -> detail context handoff
- Pass timer base/id directly (no helper write needed).

4. Remove helper dependency
- Decommission helper setup from shared addon docs.
- Keep optional backward compatibility toggle for existing users.

5. Polish
- Add subtle transitions for state changes.
- Add robust fallback handling for temporary HA gaps.

## Implementation Notes

- Prefer deriving timer base from active entity IDs over string globals.
- Keep service calls explicit and deterministic.
- If a simplification attempt breaks rendering, revert quickly and continue in the dedicated JS card branch.

## Naming Cleanup Status

- The broader card rename has started with `dashboard/snoozefest_entity_card.js`.
- `dashboard/time_picker_custom.js` remains as the legacy compatibility card during migration.
- Continue favoring the entity-oriented naming direction rather than adding new timer-only names unless a truly timer-specific card emerges later.
- Keep compatibility registration or duplicate resources in place until dashboard migration is complete.

## Multiline Input Integration Plan

- Incorporate the customized `dashboard/input_text.js` card as a shared text-input primitive in the future consolidated UI layer.
- Reuse its validated text editing behavior (autosave, min/max length checks, feedback messaging) for alarm/timer labels.
- Keep one styling/config surface for text input across alarm and timer detail views to avoid drift.
- During migration, continue registering `lovelace-multiline-text-input-card` for backward compatibility.
- After consolidated cards are stable, deprecate direct dashboard dependency on `dashboard/input_text.js` in favor of the new unified card bundle.

## Minimal Unified Timer Card Contract (Draft)

This is a practical baseline contract for the future single timer card.

### Required config

- `timer_base`: full base id, e.g. `snoozefest_timer_5` or `snoozefest_dev_timer_5`

### Optional config

- `title`: optional display title override
- `show_label_editor`: default `true`
- `show_actions`: default `true`
- `status_color_target`: `input` | `card` | `both` (default `input`)
- `status_color_default`, `status_color_inactive`, `status_color_active`, `status_color_paused`, `status_color_ringing`
- `compat_mode_helpers`: default `false`; when `true`, allows helper-based flow during migration

### Derived entities (from `timer_base`)

- `text.<base>_label`
- `text.<base>_duration`
- `sensor.<base>_status`
- `sensor.<base>_remaining`
- `sensor.<base>_remaining_friendly`
- `button.<base>_activate`
- `button.<base>_pause`
- `button.<base>_resume`
- `button.<base>_dismiss`
- `button.<base>_remove`
- `button.<base>_add_time`

### Output actions

- `start_or_restart`
- `pause`
- `resume`
- `dismiss`
- `remove`
- `add_time`
- `back_or_close`

### Guard behavior

- In `inactive` + zero duration: disable start, expose cancel/remove path.
- In `active`: enable pause.
- In `paused`: enable resume.
- In `ringing`: enable dismiss.
- In `unknown`/`unavailable`: disable all command actions and show safe fallback UI.

### Migration compatibility

- Keep current custom element names registered while rolling out the new card.
- Keep helper bridge optional (`compat_mode_helpers`) for existing dashboards.
- Remove helper dependency after list/detail direct-context flow is proven stable.
- Long term target remains a Snoozefest-owned detail card stack so dashboard flows no longer depend on unrelated third-party custom cards for core alarm/timer UX.
