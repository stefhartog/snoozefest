# Deployment Guide

Snoozefest supports two deployment models:

## 1. Local Development (Workstation)

For testing and development on Windows/Mac/Linux:

```bash
cd snoozefest
python -m venv .venv
.venv\Scripts\activate  # or source .venv/bin/activate on Unix
pip install -e .

# Run daemon
snoozefest --config config.json run
```

**Features**:
- Rapid iteration during development
- Separate MQTT namespace (`snoozefest_dev`)
- No external dependencies beyond local MQTT broker
- State stored in local JSON file

**Target Use**: Development, testing, local Home Assistant integration

---

## 2. Production (Home Assistant Add-on)

For persistent deployment on Home Assistant:

### Quick Start

1. **Install via HA UI** (when repository is published):
   - Settings → System → Add-ons → Repositories
   - Add Snoozefest repository URL
   - Search "Snoozefest" → Install → Start

2. **Verify Operation**:
   - Check add-on logs: should show `Snoozefest daemon running` and `MQTT connected`
   - Visit MQTT Explorer in HA to verify `snoozefest/` topics present

### Import Existing Alarms/Timers

If migrating from workstation dev:

1. Export dev state: `cp snoozefest_data_dev.json snoozefest_data.json` (on workstation)
2. Upload to add-on via HA File Editor: upload to `/config/snoozefest_data.json`
3. Restart add-on

See [MIGRATION.md](MIGRATION.md) for detailed migration steps.

**Features**:
- Persistent operation on HA host
- Unified MQTT namespace (`snoozefest`)
- Container-isolated from HA core
- Auto-startup and restart on failure
- Full HA device discovery and automation support

**Target Use**: Production 24/7 scheduling service

---

## Architecture Comparison

| Aspect | Local Dev | HA Add-on |
|--------|-----------|-----------|
| **OS** | Windows/Mac/Linux | Home Assistant host |
| **MQTT Prefix** | `snoozefest_dev` | `snoozefest` |
| **Persistence** | `snoozefest_data_dev.json` | `/config/snoozefest_data.json` |
| **Uptime** | Manual daemon | Auto-restart |
| **Config** | `config.json` (local) | `/config/snoozefest.json` (add-on) |
| **Use Case** | Development/Testing | Production 24/7 |
| **Coexistence** | ✅ Can run simultaneously | ✅ Can run simultaneously |

---

## Data Portability

State is stored as JSON and can be freely moved between deployments:

- Dev → Prod: Copy `snoozefest_data_dev.json` to prod `/config/snoozefest_data.json`
- Prod → Dev: Copy `/config/snoozefest_data.json` to dev `snoozefest_data_dev.json`
- Both coexist without conflict (separate MQTT namespaces prevent collision)

---

## Further Reading

- [README.md](README.md) - Operating model and command reference  
- [addon/README.md](addon/README.md) - Add-on installation and usage
- [addon/BUILD.md](addon/BUILD.md) - Building/testing the add-on locally
- [MIGRATION.md](MIGRATION.md) - Step-by-step migration from dev to production

---

## Support & Development

- **Issue Tracking**: GitHub Issues (project repository)
- **Local Development**: See quick start section
- **Add-on Development**: See [addon/BUILD.md](addon/BUILD.md)
- **MQTT Debugging**: Use MQTT Explorer or HA MQTT tools to inspect topics
