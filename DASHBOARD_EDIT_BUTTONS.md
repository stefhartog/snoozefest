# Dashboard Edit Buttons Setup

I've created updated Lovelace dashboard configurations with edit buttons for alarms and timers. These buttons automatically detect the alarm type (oneoff vs recurring) and call the appropriate update script with pre-filled data.

## Files Created

1. **alarms-dashboard-updated.yaml** - Updated alarm dashboard with edit button (pencil icon)
2. **timers-dashboard-updated.yaml** - Updated timer dashboard with edit button (pencil icon)

## What's New

### Alarm Dashboard
- **New Edit Button (pencil icon)** - Between snooze and delete buttons
  - Calls unified `snoozefest_update_alarm`
  - Empty weekdays means one-off, selected weekdays means recurring
  - Pre-fills: alarm ID, time, label, enabled status, and weekdays

### Timer Dashboard  
- **New Edit Button (pencil icon)** - Between dismiss and delete buttons
  - Calls `snoozefest_update_timer` with pre-filled data
  - Pre-fills: timer ID, hours, minutes, seconds, and label

## How It Works

The edit button uses Home Assistant button-card's JavaScript templates to:

1. **For Alarms**: Read the `kind` attribute from the switch entity
   - If `kind === "recurring"`, call recurring update script
   - Otherwise, call oneoff update script

2. **For All Types**: Extract and pre-fill fields from entity attributes and friendly_name:
   - Parse time as HH:MM from friendly name
   - Extract label
   - Get weekdays for recurring alarms
   - Get duration/label for timers

## Installation Steps

1. **Copy the alarm dashboard YAML** from `alarms-dashboard-updated.yaml` into your HA Lovelace dashboard
2. **Copy the timer dashboard YAML** from `timers-dashboard-updated.yaml` into your HA Lovelace dashboard
3. **Restart Home Assistant** (or just reload the dashboard)
4. **Click the edit button** on any alarm or timer to open the update script with pre-filled data

## Pre-filled Data Extraction

### Alarms
- **alarm_time**: Extracted from friendly_name as first HH:MM match
- **label**: Extracted from friendly_name (text before parentheses)
- **enabled**: Current state (on/off)
- **weekdays**: From `entity.attributes.weekdays` (recurring only)

### Timers
- **hours/minutes/seconds**: Calculated from `duration_seconds` attribute
- **label**: From `entity.attributes.label`

## Notes

- The dashboard uses Home Assistant's `json_attributes_topic` to automatically sync all entity attributes from snoozefest via MQTT
- The `kind` field for alarms is published automatically by the snoozefest daemon
- All scripts (`snoozefest_update_alarm`, `snoozefest_update_timer`) are already defined in snoozefest_scripts.yaml
- The edit button intelligently selects which script to call based on alarm type

## Troubleshooting

If the edit button doesn't work:

1. **Verify the scripts exist**: Check that the three update scripts are available in HA Services
2. **Check entity attributes**: In HA Developer Tools, look at the entity attributes to ensure `kind`, `label`, `weekdays`, etc. are present
3. **Verify MQTT**: Ensure snoozefest daemon is running and connected to MQTT broker
4. **Reload button-card**: If button-card JS templates seem broken, reload Home Assistant's Lovelace UI

## Customization

You can modify the grid layout by changing:
- `grid-template-areas`: Reorder buttons or remove any you don't want
- `grid-template-columns`: Adjust spacing/column widths
- Button icons: Use any `mdi:*` icon from Material Design Icons
- Colors/styling: Modify the card style section
