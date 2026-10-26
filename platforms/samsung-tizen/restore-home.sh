#!/usr/bin/env bash
# Put Samsung's stock Home back (default on most sets: com.samsung.tv.csfs)
# and optionally uninstall Fresh Home. Usage: ./restore-home.sh [TV_IP] [--remove]
set -uo pipefail
cd "$(dirname "$0")"

IP=${1:-$(python3 -c "import json;print(json.load(open('../../companion/config.json'))['ip'])" 2>/dev/null)}
SDB=${SDB:-sdb}
DEFAULT_HOME=com.samsung.tv.csfs

[ "${1:-}" = "--remove" ] && IP=${2:-$IP}

"$SDB" connect "${IP}:26101" || { echo "sdb connect failed"; exit 1; }

set_vconf () {
  local key val; key="$1"; val="$2"
  # This firmware runs an allowlisted silent shell: plain vconftool returns
  # exit 0; anything else (redirection, backticks, other binaries) = "closed".
  "$SDB" shell "vconftool set -t string -f $key $val" >/dev/null 2>&1 && { echo "set $key = $val"; return 0; }
  "$SDB" shell "0 appinstall tpk \`vconftool set -t string -f $key $val\`.tpk" >/dev/null 2>&1 && { echo "set $key = $val"; return 0; }
  echo "!! failed to set $key"; return 1
}

set_vconf db/appfw/home_appid "$DEFAULT_HOME"
set_vconf db/appfw/startup_appid "$DEFAULT_HOME"

if [ "${*:-}" != "${*--remove}" ]; then
  "$SDB" uninstall freshhome || true
  "$SDB" uninstall fhkey0001 || true
fi

echo "Samsung Home restored. Restart the TV to be safe."
