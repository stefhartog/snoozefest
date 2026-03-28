# Snoozefest Home Assistant Add-on

Local alarm and timer service with MQTT discovery for Home Assistant.

## Installation

1. Add this repository to Home Assistant Add-ons:
   - Go to Settings → System → Add-ons → Repositories
   - Add the repository URL (when published)
   - Refresh and search for "Snoozefest"
   - Click Install

2. Start the add-on and check the logs

## Configuration

The add-on configures itself automatically using Home Assistant's built-in MQTT broker.

Default settings:
- **MQTT Broker**: `mqtt://homeassistant:1883`
- **Topic Prefix**: `snoozefest` (production)
- **Client ID**: `snoozefest-addon`

## Persistent Storage

- Configuration: `/config/snoozefest.json`
- State data: `/config/snoozefest_data.json`
- Both are retained across add-on restarts

## Home Assistant Integration

Once running, Snoozefest automatically publishes MQTT discovery payloads:

- One manager device: `Snoozefest` (Purge All, Add Timer, Add Alarm buttons)
- One device per active alarm: `Snoozefest Alarm - <label>`
- One device per active timer: `Snoozefest Timer - <label>`

All devices and entities are scoped to the `snoozefest/` MQTT namespace.

See [main README](../README.md) for operating model and command topics.

## Migrating from Workstation Dev

1. **Export dev state** (on workstation):
   ```bash
   # Copy dev state file
   copy snoozefest_data_dev.json snoozefest_data.json
   ```

2. **Import to add-on**:
   - Stop the add-on
   - Copy `snoozefest_data.json` to `/config/` via SFTP or HA file editor
   - Restart the add-on

3. **Verify**:
   - Check HA MQTT Explorer for `snoozefest/` topics
   - Verify all alarms and timers appear in Home Assistant

## Support

See [main README](../README.md) for full operator documentation and command reference.
