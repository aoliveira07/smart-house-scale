FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION=0.5.0
ARG BUILD_ARCH=local

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

RUN apk add --no-cache python3 py3-pip

COPY addon_requirements.txt /addon_requirements.txt
RUN python3 -m pip install --no-cache-dir --break-system-packages -r /addon_requirements.txt

COPY run.sh /run.sh
COPY addon_app /app/addon_app
COPY backend/web /app/web

RUN chmod a+x /run.sh
WORKDIR /app

CMD [ "/run.sh" ]
