#!/usr/bin/env bash
# Interactive probe: low → auto → status-only → low again.
# Pause between steps so you can verify on the unit / native app.
#
# Usage:
#   ./tools/probe_wind_speed_experiment.sh 192.168.50.196 'device-key' '580d0df2deaf'
#   cp tools/probe_device.local.sh.example tools/probe_device.local.sh  # then:
#   ./tools/probe_wind_speed_experiment.sh

# shellcheck disable=SC1091
source "$(dirname "$0")/probe_common.sh" "$@"

echo "Wind speed experiment on $IP (proto v$VERSION)"
echo "Watch the native app and/or the unit between steps."
pause "Step 0 — baseline status (note current WdSpd / Quiet / Tur)"
show_wind

pause "Step 1 — SET Low (WdSpd=1, Quiet=0, Tur=0). App should show Low."
probe_set WdSpd=1 Quiet=0 Tur=0
show_wind

pause "Step 2 — SET Auto (WdSpd=0, Quiet=0, Tur=0). App should show Auto."
probe_set WdSpd=0 Quiet=0 Tur=0
show_wind

pause "Step 3 — STATUS ONLY (no set). Does WdSpd still show 0 or remembered 1?"
show_wind

pause "Step 4 — SET Low again (WdSpd=1)."
probe_set WdSpd=1 Quiet=0 Tur=0
show_wind

echo
echo "Done. Paste the WdSpd/Quiet/Tur lines from each step if you want help interpreting."
