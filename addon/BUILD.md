# Building the Add-on

This guide is for developers who want to build the Snoozefest add-on locally for testing.

## Prerequisites

- Docker installed
- Home Assistant instance running with MQTT broker enabled
- Network access between Docker host and HA MQTT broker

## Build Locally

```bash
cd addon/

# Build image
docker build \
  --build-arg BUILD_FROM=ghcr.io/home-assistant/base:latest \
  -t snoozefest:dev .

# Tag for testing
docker tag snoozefest:dev snoozefest:0.1.0
```

## Run for Testing

```bash
# Create config directory
mkdir -p ./config

# Run container with local config volume
docker run -it --rm \
  --name snoozefest-dev \
  -v "$(pwd)/config:/config" \
  --network host \
  snoozefest:dev
```

## Configuration

Create `./config/snoozefest.json`:

```json
{
  "mqtt_broker": "mqtt://homeassistant.local:1883",
  "mqtt_username": "mqtt",
  "mqtt_password": "password",
  "mqtt_topic_prefix": "snoozefest",
  "mqtt_client_id": "snoozefest-addon-test",
  "tick_interval": 1,
  "data_file": "/config/snoozefest_data.json"
}
```

## Verify

In another terminal, watch MQTT topics:

```bash
# Using mosquitto_sub (if installed)
mosquitto_sub -h homeassistant.local -u mqtt -P password -t 'snoozefest/#'

# Or check Home Assistant MQTT Explorer
```

## Publish to Repository

When ready to distribute:

1. Create GitHub repository for add-on (separate from Snoozefest source)
2. Push addon/ structure with multi-architecture build workflow
3. Submit to Home Assistant add-on organization (optional)
4. Users add repo URL via HA UI

See [Home Assistant Add-on Development Docs](https://developers.home-assistant.io/docs/add-ons) for details.
