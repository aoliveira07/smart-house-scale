#!/usr/bin/with-contenv bashio
set -e

export APP_DATA_DIR="/data"
export APP_VERSION="${BUILD_VERSION:-0.4.7}"
export APP_HOST="0.0.0.0"
export APP_PORT="18099"
export SMART_HOUSE_SCALE_API_URL="$(bashio::config 'api_url')"
export SMART_HOUSE_SCALE_API_TOKEN="$(bashio::config 'api_token')"
export SMART_HOUSE_SCALE_HA_CONFIG_DIR="/homeassistant"
export SMART_HOUSE_SCALE_INTEGRATION_SOURCE="/opt/smart_house_scale/custom_components/smart_house_scale"

exec python3 -m uvicorn addon_app.main:app --host "${APP_HOST}" --port "${APP_PORT}"
