#!/usr/bin/env bash
# Install Fresh Home on the TV and redirect the Home button to it.
#
#   ./install.sh [TV_IP]        (default IP comes from ../config.json)
#   SDB=/path/to/sdb ./install.sh
#
# Prereqs: TV in Developer Mode (Apps -> gear -> 123 -> 12345 -> ON,
# host = this Mac's IP, then restart the TV) and both .wgt files signed
# with your Samsung certificate (see README).
set -uo pipefail
cd "$(dirname "$0")"

IP=${1:-$(python3 -c "import json;print(json.load(open('../config.json'))['ip'])" 2>/dev/null)}
SDB=${SDB:-sdb}
MAC_IP=$(ipconfig getifaddr en0)

echo "== Fresh Home install — TV at ${IP} =="
if [ -z "${IP}" ]; then echo "no TV IP (run ../discover.py)"; exit 1; fi

"$SDB" connect "${IP}:26101" || {
  echo "!! sdb connect failed."
  echo "   On the TV: Home -> Apps -> gear (App Settings) -> press '123' on the remote"
  echo "   -> enter 12345 -> Developer mode ON -> Host PC IP = ${MAC_IP} -> TV restarts."
  exit 1;
}
"$SDB" devices

echo
echo "== backup current home settings =="
: > home-backup.txt
for key in db/appfw/home_appid db/appfw/startup_appid db/appfw/booting_appid_backup db/first_screen/type; do
  echo "$key = $("$SDB" shell "vconftool get $key" 2>/dev/null | tr -d '\r')" >> home-backup.txt
done
cat home-backup.txt
echo "(defaults on most sets: com.samsung.tv.csfs = Samsung Home)"

install_wgt () {
  # plain `sdb install` is a native sdb command and works on this firmware
  # even though `sdb shell` is restricted to a silent allowlist
  "$SDB" install "$1" && return 0
  echo "!! could not install $1"; return 1
}

echo
echo "== install launcher + home key =="
install_wgt freshhome-launcher.wgt || exit 1
install_wgt freshhome-homekey.wgt   || exit 1

set_vconf () { # key value — this firmware: silent allowlisted shell, exit-code only
  local key val; key="$1"; val="$2"
  "$SDB" shell "vconftool set -t string -f $key $val" >/dev/null 2>&1 && return 0
  echo "!! failed to set $key"; return 1
}

echo
echo "== redirect Home (via wrapper) + power-on (direct) =="
set_vconf db/appfw/home_appid   fhkey0001.key       || exit 1
set_vconf db/appfw/startup_appid freshhome.launcher || exit 1

echo
echo "done. Press HOME on the remote — Fresh Home should appear."
echo "Power-cycle to confirm it boots straight into the launcher."
echo "To undo: ./restore-home.sh"
