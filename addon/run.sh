#!/bin/bash

# Home Assistant add-on entry point for Snoozefest

set -e

# Configuration file path
CONFIG_FILE="/config/snoozefest.json"

# Create default config if it doesn't exist
if [ ! -f "$CONFIG_FILE" ]; then
    cat > "$CONFIG_FILE" << 'EOF'
{
  "mqtt_broker": "mqtt://homeassistant:1883",
  "mqtt_username": "mqtt",
  "mqtt_password": "password",
  "mqtt_topic_prefix": "snoozefest",
  "mqtt_client_id": "snoozefest-addon",
  "tick_interval": 1,
  "data_file": "/config/snoozefest_data.json"
}
EOF
    echo "Created default config at $CONFIG_FILE"
fi

# Run snoozefest daemon
exec snoozefest --config "$CONFIG_FILE" run
