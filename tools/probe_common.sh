# Shared device connection for interactive probe scripts.
# Source from experiment scripts — do not run directly.
#
# Usage (pick one):
#   ./tools/probe_wind_speed_experiment.sh 192.168.50.196 'device-key' '580d0df2deaf'
#   cp tools/probe_device.local.sh.example tools/probe_device.local.sh  # edit once
#   ./tools/probe_wind_speed_experiment.sh

set -euo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
_ROOT="$(cd "$_SCRIPT_DIR/.." && pwd)"
cd "$_ROOT"

_LOCAL="$_SCRIPT_DIR/probe_device.local.sh"
if [[ -f "$_LOCAL" ]]; then
  # shellcheck disable=SC1091
  source "$_LOCAL"
fi

IP="${1:-${IP:-}}"
KEY="${2:-${KEY:-}}"
MAC="${3:-${MAC:-}}"
VERSION="${VERSION:-2}"

if [[ -z "$IP" || -z "$KEY" || -z "$MAC" ]]; then
  _CMD="${BASH_SOURCE[1]:-$0}"
  echo "Usage: $_CMD IP KEY MAC" >&2
  echo "   or: create tools/probe_device.local.sh (see probe_device.local.sh.example)" >&2
  exit 1
fi

PROBE=(python3 tools/probe.py)

pause() {
  echo
  echo "────────────────────────────────────────"
  echo "$1"
  echo "────────────────────────────────────────"
  read -r -p "Press Enter when ready for the next step… "
  echo
}

show_wind() {
  "${PROBE[@]}" status "$IP" --key "$KEY" --mac "$MAC" --version "$VERSION" --runtime \
    | rg 'WdSpd|Quiet|Tur' || true
}

probe_set() {
  echo "[→] $*"
  "${PROBE[@]}" set "$IP" --key "$KEY" --mac "$MAC" --version "$VERSION" "$@"
}
