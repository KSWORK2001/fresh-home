# Contributing

Fresh Home is deliberately zero-dependency (Python stdlib, plain HTML/CSS/JS)
and deliberately brand-agnostic. Please keep it that way.

## The two seams

1. **Companion adapters** — `companion/<brand>.py` implementing the shared
   interface (`load_config`, `save_config`, `get_tv`, `pair`, `is_paired`,
   `catalog_apps`, `wol`, `TVError`; the TV object exposes `apps`, `launch`,
   `key`, `power`, `open_browser`). See `samsung.py` (full) or `roku.py`
   (minimal). Register your brand in `companion/tv.py::_brand()` and teach
   `discover.py` to recognize it over SSDP.
2. **Launcher device adapter** — `core/launcher/js/device.js` is the only
   platform-aware file in the UI. A new TV platform provides `launch()`,
   `openUrl()` and (optionally) richer input; everything else (grid, Get
   Apps, games, bridge) is shared.

## Rules of the road

- No frameworks, no build step for the core UI, no telemetry, no accounts.
- Test the companion with `python3 -m compileall companion` and a real TV
  when possible; mark untested protocols honestly in the README matrix.
- Catalog changes (`catalogs/apps.json`): include a source for the app ID,
  and add `alt` IDs when region/model variants are known.
- Secret hygiene: `companion/config.json`, `platforms/*/tools/certs/`,
  pairing tokens and keys are **never** committed (see `.gitignore`).

## Reporting what works on your TV

Open an issue with: brand, model, firmware year, which features worked
(discovery, pairing, app launch, keys, browser-open), and any protocol
quirks you found. The field notes in the README are the most valuable part
of this project.
