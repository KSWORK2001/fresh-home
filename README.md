# Fresh Home — a custom launcher for Samsung Tizen TVs

Two tools for taking back a Samsung Smart TV:

1. **Fresh Home (on-TV)** — a minimal, fast home screen that the remote's
   **Home button opens** and the TV **boots into**. Typographic UI, one
   app grid that quietly reorders by what you actually use, a built-in
   app catalog browser ("Get Apps"), and zero ads. Pure HTML/CSS/JS in a
   Tizen `.wgt` — no frameworks.
2. **Fresh Home (LAN)** — a zero-install web launcher served from your
   Mac: discovers the TV, pairs once, then launches any app from your
   Mac or phone in one click. Works on any 2016+ Samsung TV today, no
   sideloading involved.

Built and field-tested against a 2026 Samsung UN85M70HB (Tizen, One UI era)
— including everything that firmware does to stop you, documented in
[Field notes](#field-notes-2026-tizen-firmware) below.

---

## Status

| Component | State |
|---|---|
| LAN launcher | ✅ working end-to-end (discovery, pairing, app launching, keys, wake) |
| On-TV launcher app | ✅ built + QA'd at 1080p/4K, signing pipeline ready |
| On-TV install | ⚠️ requires a per-device Samsung certificate (2024+ TVs reject the free SDK certs) — full recipe below |
| Home-button takeover | documented; uses a wrapper app + two `vconf` keys, fully reversible |

---

## Fresh Home (LAN) — quick start

    python3 discover.py     # find the TV over SSDP (writes config.json)
    python3 tv.py pair      # press Allow once on the TV; token is cached
    python3 tv.py serve     # → http://localhost:8590 (also works from a phone)

CLI shortcuts:

    python3 tv.py launch netflix     # fuzzy-matches the app catalog
    python3 tv.py key KEY_MUTE
    python3 tv.py power
    python3 tv.py wake               # Wake-on-LAN (needs TV network standby on)

Zero dependencies — Python stdlib only, including a hand-rolled WebSocket
client for the TV's control protocol on port 8002/8001.

## Fresh Home (on-TV) — install

**What gets installed:**

- `freshhome.launcher` — the launcher. Declares the Tizen `main`
  app-control operation so it can answer Home/power-on launches.
- `fhkey0001.key` — a 0.2 s wrapper app. **Why:** the TV relaunches its
  home app through a special no-raise path (`__NO_RAISE_WINDOW`) that
  leaves a directly-registered launcher stuck behind the loading screen.
  So `db/appfw/home_appid` points at the wrapper, which starts the real
  launcher normally and exits. `db/appfw/startup_appid` (power-on)
  points at the launcher directly.

**Steps:**

1. **Developer Mode on the TV** — Home → Apps → gear (App Settings) →
   press `123` on the remote → enter `12345` → Developer mode **On**,
   Host PC IP = your computer's IP → the TV restarts. This opens
   `sdb` on port 26101 (`sdb connect <TV_IP>:26101`).

2. **A Samsung-issued certificate** (the hard gate — see field notes):
   on 2024+ firmware the TV refuses unsigned packages *and* packages
   signed with the free Tizen SDK developer certificate. Mint a real
   author + DUID-bound distributor certificate with your (free) Samsung
   account:

       pip3 install cryptography certifi
       python3 on-tv/tools/make_samsung_cert.py <TV_DUID> \
           --out on-tv/tools/certs/samsung

   Your browser opens a Samsung sign-in page; the token stays in memory.
   The DUID is on the TV under Settings → Support → Contact Samsung.
   (Script adapted from anandhuremanan/samsung-tizen-clock-app — the CA
   download it needs happens automatically the first time.)

3. **Build, sign, install:**

       cd on-tv
       ./build.sh                       # packages both widgets
       cd tools && ./build-signed.sh    # signs with your Samsung certs
       cd .. && ./install.sh            # sdb install + flip Home + backup

   `sign.js` replicates Samsung's own extension signer (same SignedInfo
   layout, constant `#prop` digests, exclusive C14N quirks) in pure Node,
   using the extension's node-forge. No Tizen Studio, no Java.

4. Press **Home**. Power-cycle once to confirm boot-into-launcher.

**Rollback:** `on-tv/restore-home.sh` puts the stock Samsung Home back
(`com.samsung.tv.csfs`) and can uninstall both widgets.

## Games & controllers

The launcher ships with a **Games** tile (pinned, next to Web Browser) — three
bundled, offline, zero-tracking games (Snake, Breakout, 2048) that run inside
the launcher. Input reaches them three ways, all merged into one API:

1. **The remote itself** — d-pad + OK work in every game.
2. **A controller paired directly to the TV** — pair a Bluetooth gamepad or
   plug a USB one into the TV; the app declares Samsung's gamepad metadata
   (`http://samsung.com/tv/metadata/gamepad` = `extend`) so the browser
   Gamepad API feeds the games. This is the lowest-latency path.
3. **The Controller Bridge** — for controllers the TV won't accept:
   run `python3 tv.py serve` on your Mac and open
   **http://your-mac:8590/bridge** on the Mac (or a phone). That page reads
   any browser-visible gamepad (plus WASD/arrows as a keyboard fallback) and
   streams it over a WebSocket to the Games screen on the TV. Set the bridge
   host on the TV once: Games → Bridge Host (d-pad keyboard, no typing on a
   phone needed).

The bridge relay is built into `tv.py serve` (`/ws/bridge` in, `/ws/feed`
out) — a hand-rolled WebSocket server, still zero dependencies.

## Design

The launcher UI is deliberately typographic: no icon assets, no gradients,
one white focus ring. Each tile carries the app's initial in its brand
color (lightness-normalized so every mark reads on near-black), a large
clock anchors the composition, and motion is limited to a 180 ms focus
transition and a 240 ms scroll. The stage is a fixed 1920×1080 canvas
scaled to the real viewport — on Tizen, web-app UI renders at 1920×1080
on every panel (UHD included) and the compositor upscales 2×, so the UI
is all-vector and stays crisp.

The **Get Apps** tile opens a catalog of ~100 Tizen apps (IDs from
community-maintained lists); OK adds/removes tiles with the d-pad —
no typing app IDs with a remote — and a row at the top jumps into the
Samsung App Store for real downloads.

## Field notes: 2026 Tizen firmware

Everything learned the hard way on a UN85M70HB (Oct 2026 firmware),
much of it undocumented elsewhere:

- **`sdb install` fails silently.** It pushes the file, prints progress,
  exits 0 — and the package manager drops unsigned/rejected packages
  without a single line of output. Ground truth: `sdb uninstall <pkg>`
  prints `package is not in pkgmgr_info DB / package is not installed`
  — use it as an install probe.
- **The signature gate is strict.** Rejected: unsigned, SDK
  developer-CA-signed (author + sdk-public distributor), author-only.
  Accepted path: Samsung-account author cert + DUID-bound distributor
  cert (see install step 2). This matches what other 2024+ TV owners
  have reported.
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
  (wrapper pattern, see above) + `db/appfw/startup_appid` + declaring
  the `main` app-control operation in `config.xml` (manifest schema
  2.4+, `reload="disable"`).
- Web-app UI renders at 1920×1080 on all panels; 4K is video-only.

## Repo layout

    discover.py, samsung.py, tv.py, index.html   LAN launcher (stdlib-only)
    bridge.html                                   controller bridge page (/bridge)
    apps.json                                     core app catalog (shared)
    apps-extra.json                               extended catalog (Get Apps)
    on-tv/launcher/                               the .wgt launcher source
    on-tv/launcher/games/                         bundled web games (offline)
    on-tv/launcher/js/input.js                    unified input (keys/gamepad/bridge)
    on-tv/homekey/                                the Home-key wrapper .wgt
    on-tv/tools/sign.js                           wgt signer (Samsung-compatible)
    on-tv/tools/make_samsung_cert.py              Samsung-account certificate mint
    on-tv/{build,install,restore-home}.sh         build / install / rollback

`config.json` (TV IP + pairing token) and everything under
`on-tv/tools/certs/` are gitignored — they are yours alone.

## Credits & sources

- [smakosh — replacing a Samsung TV home screen with an AI agent](https://smakosh.com/blog/replacing-samsung-tv-home-screen-with-ai)
  (the `__NO_RAISE_WINDOW` wrapper pattern, 2024+ cert gate)
- [arn0-tv](https://github.com/NelsonEU/arn0-tv) (home_appid / app-control
  operation mechanics)
- [anandhuremanan/samsung-tizen-clock-app](https://github.com/anandhuremanan/samsung-tizen-clock-app)
  (`make_samsung_cert.py`)
- Signing algorithm derived from the **tizensdk.tizentv** VS Code extension
  (Apache-2.0)
- App IDs from [xchwarze/samsung-tv-ws-api](https://github.com/xchwarze/samsung-tv-ws-api/blob/master/APPLICATIONS.md),
  [ollo69/ha-samsungtv-smart](https://github.com/ollo69/ha-samsungtv-smart/blob/master/docs/App_list.md),
  [rs.ltd](https://rs.ltd/apps/remote-control-tv/custom-apps/samsung)
- Context: [TechCrunch — people are using AI to make their smart TVs dumb again](https://techcrunch.com/2026/10/19/people-are-using-ai-to-make-their-smart-tvs-dumb-again/)

## License

MIT — see [LICENSE](LICENSE). Do what you want; breakage is your own.
Modifying your own TV is legal; just know that firmware updates can
revert the Home redirect (re-run `install.sh`) and that a bad day can
require `restore-home.sh` — which is why it exists.
