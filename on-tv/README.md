# Fresh Home — the on-TV launcher

A minimal, fast home screen for your Samsung TV (Tizen). The Home button
opens it; power-on boots into it. Fully reversible.

- `launcher/` — the launcher widget (`freshhome.launcher`)
- `homekey/` — 0.2 s wrapper app (`fhkey0001.key`). The TV relaunches its
  home app through a special no-raise path that leaves a directly registered
  launcher stuck behind the loading screen — so Home points at the wrapper,
  which starts the real launcher normally and exits. Power-on
  (`db/appfw/startup_appid`) points at the launcher directly.

## Setup (one-time, ~20 min)

**1. Developer Mode on the TV** (needs the TV and this Mac on the same Wi-Fi):

- Home → **Apps** → gear icon (App Settings) → press **123** on the remote
  → enter **12345** → Developer mode **On**
- Host PC IP = this Mac's IP (`ipconfig getifaddr en0`)
- Confirm → the TV **restarts**. This opens `sdb` on port 26101.

**2. Tizen Studio + certificate** (free, needs a Samsung account):

- Install [Tizen Studio](https://developer.samsung.com/smart-tv/extend/installing-tizen-studio/) —
  you only need the base tools + TV SDK (the `sdb` binary and Certificate
  Manager; skip the IDE if offered the choice).
- Certificate Manager → **+** → **Samsung TV** → sign in with your Samsung
  account → create author + distributor cert (defaults are fine).
- Note: 2024+ TVs may reject free CLI-generated certs; a certificate created
  through Certificate Manager with a Samsung-account sign-in is the reliable
  path (and what the community ended up using).

**3. Sign + build + install:**

    # sign both wgt files with your cert (Tizen Studio CLI):
    export PATH="$PATH:/Applications/tizen-studio/tools/ide/bin"
    tizen.sh sign -a myprofile --in freshhome-launcher.wgt
    tizen.sh sign -a myprofile --in freshhome-homekey.wgt

    ./build.sh                 # rebuilds (re-sign after rebuilding!)
    ./install.sh               # installs + redirects Home, saves home-backup.txt

If your `sdb` isn't on `PATH`: `SDB=/Applications/tizen-studio/tools/ide/bin/sdb ./install.sh`

**4. Test:** press HOME → Fresh Home. Power-cycle → boots into Fresh Home.

## Day-to-day

- D-pad to move, OK to open. The grid quietly reorders by what you actually
  use. BACK snaps to the first tile. Live TV is the anchor tile.
- Catalog lives in `../apps.json` (shared with the Mac/phone web launcher).
  Edit → `./build.sh` → re-sign → `./install.sh`.

## Undo / troubleshooting

- `./restore-home.sh` — stock Samsung Home back (default `com.samsung.tv.csfs`;
  your TV's original values were saved to `home-backup.txt` at install).
- `./restore-home.sh --remove` — also uninstalls both widgets.
- A firmware update may revert the Home redirect or refuse the app — just
  re-run `./install.sh`, or restore if anything misbehaves.
- If the launcher misbehaves, HOME long-press / Settings still work: only the
  Home key routing changes; inputs, volume, settings are untouched.
