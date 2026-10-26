# Android TV / Google TV / Fire TV

Android-based TVs are the *easiest* platform for home-screen replacement —
third-party launchers are a first-class concept there:

- **On-TV launcher:** the community already has excellent native launchers —
  [Projectivy Launcher](https://github.com/PIxar2280/Projectivy-Launcher),
  FLauncher, ATV Launcher, and the AI-driven
  [dumbtv](https://github.com/muzzamilhsabuwala/dumbtv) /
  [cleanyourtv](https://github.com/Gathin23/cleanyourtv) debloat flows.
  Use one of those as the home screen; Fresh Home's value-add on Android is
  the companion below. (If you want Fresh Home's UI *as* the launcher, wrap
  `core/launcher/` in a WebView shell APK with a HOME intent and a JS bridge
  implementing `device.js` — PRs welcome.)
- **Companion (now built):** `companion/androidtv.py` drives any Android TV
  (TCL and Onn Google TV models, Sony Bravia Google TV, Hisense, Shield,
  Fire TV) over ADB: keys, app list + launch, VIEW-intent URL opening.
  Enable Developer Options → Network
  debugging (ADB over TCP) on the TV, then `adb connect <tv-ip>:5555`.
  Everything the phone remote does maps to ADB commands:
  keys via `adb shell input keyevent` (KEYCODE_DPAD_UP…), apps via
  `adb shell monkey -p <package> 1` or `am start`. A `companion/androidtv.py`
  adapter implementing the same interface as `samsung.py` is a ~100-line
  contribution — welcome!
- **Debloat:** `adb shell pm uninstall -k --user 0 <package>` — see the
  [TechCrunch piece](https://techcrunch.com/2026/10/19/people-are-using-ai-to-make-their-smart-tvs-dumb-again/)
  for the general flow.
