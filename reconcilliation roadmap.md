- Idea logged (2026-04-02): optional reserved-slot mode (e.g., 10 alarm + 10 timer devices pre-created and reused) to reduce MQTT/HA entity churn and stale-device artifacts.
- Preferred first approach: keep create/delete model and harden discovery reconciliation/cleanup.
- Reconciliation hardening plan (next session):
  1) On startup/reconnect, republish valid discovery for active IDs.
  2) Publish retained empty discovery payloads for orphaned/removed IDs.
- Bug note for next pass: VA-created timers are correctly marked temporary, but dismiss/remove flow does not clear the timer helper id, leaving stale detail context.

  3) Add manual manager action/command for discovery reconcile.
  4) Make list UI ignore unavailable/ghost entities more aggressively.
- Reserved-slot mode stays as optional advanced fallback if reconciliation hardening is insufficient.
