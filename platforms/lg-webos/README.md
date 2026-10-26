# LG webOS

webOS is the friendliest TV platform for this project:

- **Companion (works today):** full LAN remote + launcher via the SSAP
  protocol (`companion/lg.py`). Pair once — the TV shows a permission
  prompt and returns a client-key that is cached forever. Unlike Samsung
  Tizen, webOS still exposes the **live installed-app list**, so the web
  launcher and phone remote show your actual apps.
  Status: implemented from the SSAP spec and community clients; **not yet
  validated on physical hardware** — testing reports very welcome.
- **On-TV launcher:** webOS allows third-party home screens (Samsung does
  not). The core launcher (`../../core/launcher/`) packages as an `.ipk`
  via `ares-package` from the
  [webOS TV SDK](https://webostv.developer.lge.com/develop/tools/sdk-introduction),
  installs with `ares-install` (Dev Mode on the TV), and can be set as the
  default Home in Settings. You'll need to provide a `device.js` platform
  adapter that launches apps via the webOS `webOS.launch()` bridge —
  see `core/launcher/js/device.js` for the seam. Contributions welcome.
- Recommended reading: [Projectivy Launcher](https://github.com/PIxar2280/Projectivy-Launcher)
  (a native webOS launcher — proof the home takeover is sanctioned by the
  platform) and [webos-ssap-web](https://github.com/Informatic/webos-ssap-web).
