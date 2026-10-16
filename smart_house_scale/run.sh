#!/usr/bin/with-contenv bashio
set -e

export APP_DATA_DIR="/data"
export APP_VERSION="${BUILD_VERSION:-0.7.4}"
export APP_HOST="0.0.0.0"
export APP_PORT="18099"
export SMART_HOUSE_SCALE_API_URL="$(bashio::config 'api_url')"
export SMART_HOUSE_SCALE_API_TOKEN="$(bashio::config 'api_token')"
export SMART_HOUSE_SCALE_WEIGHT_ENTITY="$(bashio::config 'weight_entity_id')"
export SMART_HOUSE_SCALE_MQTT_DISCOVERY_PREFIX="$(bashio::config 'mqtt_discovery_prefix')"

# The Supervisor Services API supplies the broker credentials without storing
# them in the repository or exposing them through the App configuration UI.
if MQTT_HOST_VALUE="$(bashio::services mqtt "host" 2>/dev/null)" && [ -n "${MQTT_HOST_VALUE}" ]; then
  export MQTT_HOST="${MQTT_HOST_VALUE}"
  export MQTT_PORT="$(bashio::services mqtt "port" 2>/dev/null || echo 1883)"
  export MQTT_USER="$(bashio::services mqtt "username" 2>/dev/null || true)"
  export MQTT_PASSWORD="$(bashio::services mqtt "password" 2>/dev/null || true)"
fi

exec python3 -m uvicorn addon_app.main:app --host "${APP_HOST}" --port "${APP_PORT}"
