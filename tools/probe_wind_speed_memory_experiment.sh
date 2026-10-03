#!/usr/bin/env bash
# Test whether Quiet / Turbo remember the last WdSpd, and what status reports.
#
# Usage:
#   ./tools/probe_wind_speed_memory_experiment.sh 192.168.50.196 'device-key' '580d0df2deaf'
#   cp tools/probe_device.local.sh.example tools/probe_device.local.sh  # then:
#   ./tools/probe_wind_speed_memory_experiment.sh

# shellcheck disable=SC1091
source "$(dirname "$0")/probe_common.sh" "$@"

echo "Quiet/Turbo WdSpd memory test on $IP (proto v$VERSION)"
echo "Auto = WdSpd 0 with Quiet=0 and Tur=0 (not a separate wire key)."
echo

pause "Step 0 — baseline"
show_wind

pause "Step 1 — SET Low (WdSpd=1). Note app fan step."
probe_set WdSpd=1 Quiet=0 Tur=0
show_wind

pause "Step 2 — SET Quiet only (Quiet=2, no WdSpd). Set reply may omit WdSpd; next poll should remember 1."
probe_set Quiet=2 Tur=0
show_wind

pause "Step 3 — STATUS ONLY while quiet. WdSpd still 0 or remembered 1?"
show_wind

pause "Step 4 — SET Low again (WdSpd=1, clears quiet). Back to low?"
probe_set WdSpd=1 Quiet=0 Tur=0
show_wind

pause "Step 5 — SET Medium (WdSpd=3). Note app."
probe_set WdSpd=3 Quiet=0 Tur=0
show_wind

pause "Step 6 — SET Turbo only (Tur=1, no WdSpd). Status should show Tur=1 and WdSpd=3 if it remembers medium."
probe_set Tur=1 Quiet=0
show_wind

pause "Step 7 — STATUS ONLY while turbo. WdSpd still 3 or forced to 5?"
show_wind

pause "Step 8 — SET Medium again (WdSpd=3, clears turbo). Restored?"
probe_set WdSpd=3 Quiet=0 Tur=0
show_wind

echo
echo "Done. Key questions:"
echo "  • Quiet: does status poll remember last WdSpd (e.g. 1) while Quiet=2?"
echo "  • Turbo: with Tur=1 only (no WdSpd), does status poll remember last WdSpd (e.g. 3)?"
echo "  • After clearing quiet/turbo, does WdSpd match what you had before?"
