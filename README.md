# Mitsubishi Comfort for Home Assistant (cloud-control fork)

A custom integration for Mitsubishi minisplit systems that use the Kumo Cloud app, forked from
[nikolairahimi/ha-mitsubishi-comfort](https://github.com/nikolairahimi/ha-mitsubishi-comfort). It
uses the [mitsubishi-comfort](https://github.com/nikolairahimi/mitsubishi-comfort) library.

Units are controlled directly over your local network when their LAN credentials are known. Units
without local credentials are controlled through the Kumo Cloud API instead of being left out, and
the integration keeps trying to get their local credentials so it can move them to LAN control.

Compared with upstream, this fork adds:

- **Cloud control fallback** for units without local credentials. These get a climate entity plus
  temperature and humidity sensors; sensors that need the LAN adapter (Wi-Fi signal, uptime,
  external sensor) are only created for locally controlled units.
- **Automatic switch to LAN** once a cloud-controlled unit's local credentials are retrieved.
- **No startup delay**: the credential retry runs in the background.
- Home Assistant core conventions: entity names from translations, errors when a unit rejects a
  command, credentials kept in the config entry, and a test suite on Home Assistant's test harness.

Home Assistant also ships a core integration with the domain `mitsubishi_comfort`. When this custom
copy is installed, it takes precedence over the core one.

## Entities

Each indoor unit gets a climate entity (HVAC mode, setpoints, fan speed and vane direction) and a
filter binary sensor. Sensors cover room temperature and humidity, Wi-Fi and external sensor signal,
external sensor battery and uptime; Kumo Stations report the outdoor temperature. Only the climate
entity, filter sensor and room temperature sensor are enabled by default.

## Installation

1. Copy `homeassistant/components/mitsubishi_comfort` into `<config>/custom_components/`.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and choose **Mitsubishi Comfort**.

### Configuration parameters

| Parameter | Description |
| --- | --- |
| Username | The email address you use to sign in to the Kumo Cloud app. |
| Password | The password for your Kumo Cloud account. |

Only one account can be configured.

### Options

| Option | Default | Description |
| --- | --- | --- |
| Connection timeout | 1.2 s | How long to wait when opening a connection to a unit on the local network. |
| Response timeout | 8 s | How long to wait for a unit on the local network to answer a request. |

## Data updates

Each unit is polled every 60 seconds. A unit is marked unavailable after three consecutive missed
polls and recovers on the next successful one. LAN addresses are found by matching the units' MAC
addresses against Home Assistant's DHCP discovery.

## Removal

1. Go to **Settings → Devices & services**, open **Mitsubishi Comfort** and delete the entry.
2. Delete `<config>/custom_components/mitsubishi_comfort` and restart Home Assistant.

## Development

The integration and its tests use Home Assistant core's layout. Run the tests from a
[core development checkout](https://developers.home-assistant.io/docs/development_environment),
replacing core's own copy of the integration:

```bash
rm -rf <core>/homeassistant/components/mitsubishi_comfort <core>/tests/components/mitsubishi_comfort
cp -r homeassistant/components/mitsubishi_comfort <core>/homeassistant/components/
cp -r tests/components/mitsubishi_comfort <core>/tests/components/
cd <core>
pytest tests/components/mitsubishi_comfort
python -m script.hassfest --integration-path homeassistant/components/mitsubishi_comfort
```

Lint with `ruff check . && ruff format --check .` from this repository; the ruff settings in
`pyproject.toml` and `tests/ruff.toml` are core's.
