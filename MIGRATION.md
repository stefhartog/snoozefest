# Migration Guide: Workstation Dev → HA Add-on Production

This guide walks through migrating Snoozefest from workstation development to Home Assistant Add-on production deployment.

## Overview

- **Workstation Dev**: `snoozefest_dev` MQTT namespace, local Windows environment
- **HA Add-on Prod**: `snoozefest` MQTT namespace, containerized in Home Assistant

Both instances can coexist without conflict due to separate topic prefixes.

## Pre-Migration Checklist

- [ ] Dev instance stable and all alarms/timers created and tested
- [ ] Previous dev instance logs reviewed for any pending fixes
- [ ] HA Add-on repository cloned or ready for deployment
- [ ] Home Assistant MQTT broker running with `mqtt` user configured
- [ ] Backup of `snoozefest_data_dev.json` created

## Step 1: Export Dev State

On your workstation, verify dev instance is running and state is current:

```bash
# Workstation PowerShell
cd c:\Users\stefh\snoozefest

# Check dev data file exists
ls snoozefest_data_dev.json

# View current alarms and timers (optional)
& ".\.venv\Scripts\python.exe" -m snoozefest --config config.json show

# Copy dev state to transport name
cp snoozefest_data_dev.json snoozefest_data_export.json
```

## Step 2: Deploy HA Add-on

### Option A: Via Home Assistant UI (when repo is published)

1. Go to **Settings → System → Add-ons → Repositories**
2. Add the Snoozefest repository URL
3. Refresh and search for "Snoozefest"
4. Click **Install**
5. Configure MQTT credentials (if different from Home Assistant default)
6. Click **Start**
7. Check **Logs** to confirm:
   ```
   Snoozefest daemon running (tick=1s)
   MQTT connected to homeassistant:1883
   ```

### Option B: Manual Docker Deployment (for testing)

```bash
# On HA host (via SSH or terminal)
cd /path/to/snoozefest/addon

# Build image
docker build -t snoozefest:latest .

# Run container with config volume
docker run -d \
  --name snoozefest \
  -v /share/snoozefest-config:/config \
  -e MQTT_BROKER=mqtt://homeassistant:1883 \
  -e MQTT_USERNAME=mqtt \
  -e MQTT_PASSWORD=<password> \
  snoozefest:latest
```

## Step 3: Import Dev State to Production

### Via Home Assistant File Editor (Easiest)

1. Install **File Editor** add-on (if not present)
2. Upload `snoozefest_data_export.json` to `/config/` folder
3. Rename to `snoozefest_data.json`
4. Restart Snoozefest add-on
5. Verify import in logs and HA MQTT Explorer

### Via HA SSH Terminal

```bash
# SSH into HA host
# Copy exported state to add-on config directory
cp /path/to/export/snoozefest_data_export.json /config/snoozefest_data.json

# Restart add-on
ha addon restart snoozefest
```

### Via SFTP (if configured)

1. Open SFTP client pointing to HA host
2. Navigate to `/config/`
3. Upload `snoozefest_data_export.json`
4. Rename to `snoozefest_data.json`
5. Restart add-on

## Step 4: Verify Production Instance

1. **Check MQTT Topics**:
   - Open **MQTT Explorer** or HA MQTT UI
   - Verify `snoozefest/` topics are present (NOT `snoozefest_dev/`)
   - Verify all alarms and timers appear in topic structure

2. **Check Home Assistant Devices**:
   - Go to **Settings → Devices & Services → MQTT**
   - Filter for "Snoozefest" (NOT "Snoozefest Dev")
   - Verify manager device and all alarm/timer devices listed

3. **Test Manager Actions**:
   - Click **Purge All** button → should clear all alarms/timers
   - Add new alarm via Home Assistant MQTT call service
   - Verify new alarm appears in device list

4. **Check Add-on Logs**:
   - Verify no errors or connection warnings
   - Should show steady tick (every 1 second)

## Step 5: Decommission Dev Instance (Optional)

Once production is stable, you can decommission the workstation dev instance:

```bash
# Workstation PowerShell - stop dev daemon
$existing = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'snoozefest.*config\.json.*run' }
if ($existing) { $existing | ForEach-Object { Stop-Process -Id $_.ProcessId -Force } }

# Keep .venv and source code for future dev/testing
# Optionally remove config.json and snoozefest_data_dev.json
rm config.json
rm snoozefest_data_dev.json
```

## Step 6: Archive Dev Environment (Recommended)

Keep the dev environment available for future testing and development:

```bash
# Workstation - create clean dev config for future use
@{
    mqtt_broker = "mqtt://homeassistant.local:1883"
    mqtt_username = ""
    mqtt_password = ""
    mqtt_topic_prefix = "snoozefest_dev"
    mqtt_client_id = "snoozefest-dev-test"
    tick_interval = 1
    data_file = "snoozefest_data_dev.json"
} | ConvertTo-Json | Out-File config.json

# Keep archive of exported state
cp snoozefest_data_export.json "archive\snoozefest_data_prod_import_$(Get-Date -Format 'yyyyMMdd').json"
```

## Troubleshooting

### Issue: Add-on starts but MQTT not connecting

**Diagnosis**: Check add-on logs for connection error.

**Solution**:
1. Verify MQTT broker is running (check HA Settings → System → MQTT)
2. Verify `mqtt` user exists and password is correct
3. Verify add-on config has correct broker address and credentials
4. Restart add-on

### Issue: Dev and prod instances conflicting on same MQTT broker

**Diagnosis**: Both instances publishing to same topic prefix.

**Solution**:
- **Dev remains on**: `snoozefest_dev/` prefix
- **Prod on**: `snoozefest/` prefix
- Check `config.json` (workstation) and `/config/snoozefest_data.json` (HA) to verify prefix values
- Restart affected instances

### Issue: Alarms/timers missing after import

**Diagnosis**: State import failed or data file corrupted.

**Solution**:
1. Check `/config/snoozefest_data.json` exists and is readable
2. Verify file contains valid JSON: `jq . /config/snoozefest_data.json`
3. If corrupted, restore from backup: `cp snoozefest_data_export.json /config/snoozefest_data.json`
4. Restart add-on

### Issue: Add-on restarts repeatedly

**Diagnosis**: Check logs for crash or exception.

**Solution**:
1. View full logs: `ha addon logs snoozefest --follow`
2. Look for Python stack trace or missing dependency
3. Common causes: missing MQTT broker, misconfigured credentials, corrupted state file
4. Contact project or review main README troubleshooting

## Rollback to Dev

If production instance is unstable, you can temporarily revert to dev-only:

```bash
# Workstation - restart dev instance
& ".\.venv\Scripts\python.exe" -m snoozefest --config config.json run

# HA - stop production add-on (via UI or SSH)
ha addon stop snoozefest
```

No data loss occurs; dev state (`snoozefest_data_dev.json`) remains separate from prod.

## Next Steps

- Read [main README](../README.md) for operating model and command reference
- Consider setting up separate MQTT user for add-on with restricted ACL
- Monitor add-on logs for first week of production
- Archive workstation dev environment for future testing

