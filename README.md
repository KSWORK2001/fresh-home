# Fresh Home — take back your smart TV

A minimal, fast, ad-free home experience for your TV — whatever the brand.
One core launcher UI, one zero-dependency companion server, and a small
adapter per platform. No frameworks, no telemetry, no accounts.

| What | Samsung Tizen (2016+) | LG webOS | Roku | Android TV / Google TV / Fire TV |
|---|---|---|---|---|
| Discovery + pairing | ✅ field-tested (2026 model) | ✅ implemented *(needs hardware validation)* | ✅ (no pairing needed) | via ADB *(adapter welcome)* |
| Web launcher + phone remote | ✅ | ✅ | ✅ | planned |
| Live installed-app list | ❌ firmware removed it — curated catalog instead | ✅ | ✅ | n/a |
| Open URL in TV browser | ✅ | ✅ | ❌ | ❌ |
| On-TV home screen takeover | ✅ hard-won recipe (signed sideload + `home_appid`) | ✅ platform-sanctioned — packaging guide | n/a | ✅ easiest platform — see platform notes |
| Bundled games + controller bridge | ✅ | via core launcher | — | — |

Start in `companion/`:

    cd companion
    python3 tv.py discover        # finds TVs of any supported brand
    python3 tv.py pair            # once (Roku skips this)
    python3 tv.py serve           # web launcher + phone remote + gamepad bridge
                                  #   → http://localhost:8590  (/remote on a phone)

CLI: `launch netflix` · `key KEY_MUTE` · `power` · `browse <url>` · `wake`.

- **Web launcher** (`/`) — one-click app tiles for Mac/phone.
- **Phone remote** (`/remote`) — swipe/tap touchpad, volume, power, app
  chips, cloud-gaming chips. Add to home screen for an app-like remote.
- **Controller bridge** (`/bridge`) — stream any gamepad from your
  computer/phone to the bundled web games on the TV.

## The on-TV launcher (Fresh Home proper)

A typographic, monochrome home screen — clock, one app grid that reorders
by use, a Get Apps catalog browser, bundled offline games, cloud-gaming
shortcuts. The Home button opens it; power-on boots into it. The same UI
(`core/launcher/`) packages per platform:

- **`platforms/samsung-tizen/`** — the full, field-tested route: unsigned
  → SDK-signed → Samsung-account certificate saga, the pure-Node `.wgt`
  signer, the Home-key wrapper pattern, install/rollback scripts, and the
  [field notes](#field-notes-2026-tizen-firmware) below. This is the
  hardest platform; everything needed to repeat it is in the box.
- **`platforms/lg-webos/`** — SSAP companion adapter (implemented, needs
  hardware validation) + `.ipk` packaging guide. webOS allows third-party
  home screens natively.
- **`platforms/android-tv/`** — ADB notes + pointers; PRs for an adapter
  or a WebView shell APK welcome.

## Design

No icon assets, no gradients, one white focus ring. Each tile carries the
app's initial in its brand color (lightness-normalized to read on
near-black); motion is limited to a 180 ms focus transition. The stage is a
fixed 1920×1080 canvas scaled to the real viewport (Tizen renders web-app
UI at 1080p on every panel; the compositor upscales — all-vector UI stays
crisp).

## Field notes: 2026 Tizen firmware

Everything learned the hard way on a UN85M70HB (Oct 2026 firmware), much
of it undocumented elsewhere:

- **`sdb install` fails silently.** It pushes the file, prints progress,
  exits 0 — and the package manager drops unsigned/rejected packages
  without a single line of output. Ground truth: `sdb uninstall <pkg>`
  prints `package is not in pkgmgr_info DB / package is not installed`
  — use it as an install probe.
- **The signature gate is strict.** Rejected: unsigned, SDK
  developer-CA-signed (author + sdk-public distributor), author-only.
  Accepted path: Samsung-account author cert + DUID-bound distributor
  cert (see `platforms/samsung-tizen/tools/make_samsung_cert.py`).
- **`sdb shell` is a silent allowlist.** Most commands return nothing at
  all. `vconftool set -t string -f <key> <value>` executes (exit 0);
  anything with redirection, backticks, or most other binaries returns
  `closed` (exit 1). Exit codes are the only feedback channel. The
  community's older `0 appinstall` backtick-injection trick is dead on
  this firmware.
- **`screenshot`, `dlog`, `pull` from `/tmp`** — all blocked. You cannot
  see the TV's screen or logs from sdb; verification is behavioral.
- **The WebSocket control API (`:8002`) lost `ms.webapi`** — the classic
  `ed.installed_app.get` app-list subscription replies
  `unrecognized method`. App launching (`RunApp`) still works. Also:
  commands sent before the `ms.channel.ready` / `ms.channel.connect`
  event are rejected with `No Authorized` — wait for the greeting.
- **Home routing** works exactly as on earlier Tizen: `db/appfw/home_appid`
  (wrapper pattern — the TV relaunches home via `__NO_RAISE_WINDOW`, so a
  directly-registered launcher sticks behind the loading screen; use a
  0.2 s wrapper app that starts the real launcher and exits) +
  `db/appfw/startup_appid` + declaring the `main` app-control operation
  in `config.xml` (manifest schema 2.4+, `reload="disable"`).
- Web-app UI renders at 1920×1080 on all panels; 4K is video-only.

## Repo layout

    core/launcher/            the brand-agnostic launcher UI
      js/device.js            the ONLY platform-aware file (launch/openUrl seam)
      games/                  bundled offline games (Snake, Breakout, 2048)
      js/input.js             unified input: remote + gamepad + bridge
    companion/                zero-dependency server + CLI + web UIs
      samsung.py lg.py roku.py   brand adapters (SSAP, ECP, Samsung WS)
      tv.py                   CLI + web server + phone remote + bridge relay
      remote.html bridge.html index.html
    catalogs/                 shared app catalogs (core + extended)
    platforms/
      samsung-tizen/          .wgt packaging, signer, cert minting, field notes
      lg-webos/  android-tv/  platform guides and adapters (growing)

`companion/config.json` (TV IP + pairing secrets) and everything under
`platforms/*/tools/certs/` are gitignored — they are yours alone.

## Credits & sources

- [smakosh — replacing a Samsung TV home screen with an AI agent](https://smakosh.com/blog/replacing-samsung-tv-home-screen-with-ai)
- [arn0-tv](https://github.com/NelsonEU/arn0-tv) ·
  [anandhuremanan/samsung-tizen-clock-app](https://github.com/anandhuremanan/samsung-tizen-clock-app)
  (cert script) · signing algorithm derived from the **tizensdk.tizentv**
  VS Code extension (Apache-2.0)
- App IDs from [xchwarze/samsung-tv-ws-api](https://github.com/xchwarze/samsung-tv-ws-api/blob/master/APPLICATIONS.md),
  [ollo69/ha-samsungtv-smart](https://github.com/ollo69/ha-samsungtv-smart/blob/master/docs/App_list.md),
  [rs.ltd](https://rs.ltd/apps/remote-control-tv/custom-apps/samsung)
- webOS SSAP details from [go-webos](https://pkg.go.dev/github.com/kaperys/go-webos)
  and the [LG developer forum](https://forum.webostv.developer.lge.com/t/sending-remote-press-via-the-command-line/19147)
- Context: [TechCrunch — people are using AI to make their smart TVs dumb again](https://techcrunch.com/2026/10/19/people-are-using-ai-to-make-their-smart-tvs-dumb-again/)

## License

MIT — see [LICENSE](LICENSE). Modifying your own TV is legal; firmware
updates can revert the Home redirect (re-run the installer) and a bad day
can require the rollback script — which is why it exists.
