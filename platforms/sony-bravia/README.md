# Sony Bravia (IP Control)

Sony's TVs speak their own IP-Control API over HTTP — no sideloading, no
dev mode, just a Pre-Shared Key:

1. On the TV: **Settings → Network → Home Network Setup → IP Control →
   Authentication → Normal and Pre-Shared Key** — set any passphrase.
2. `python3 tv.py pair` — enter that passphrase once (cached in
   `companion/config.json`).

What you get (`companion/sony.py`):

- Keys via the IRCC endpoint (full standard code table built in — d-pad,
  volume, channel, media, Netflix/YouTube hotkeys)
- **Live app list** with launch URIs (`appControl.getApplicationList` →
  `avContent.setPlayContent`)
- Power off (IRCC) + Wake-on-LAN for power on

Google TV-era Bravias can alternatively use the Android TV path
(`platforms/android-tv/`) for ADB control and third-party launchers — the
IP-Control adapter is simpler and works on the whole line.

Sources: [Sony BRAVIA IP control](https://pro-bravia.sony.net/remote-display-control),
community [IRCC code tables](https://gist.github.com/henrik/32bb3b037b728b81a560d3676c7cfcf7)
and [API summary](https://gist.github.com/kalleth/e10e8f3b8b7cb1bac21463b0073a65fb).
Not yet validated on physical hardware — reports welcome (see CONTRIBUTING).
