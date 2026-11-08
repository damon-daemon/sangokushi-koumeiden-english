#!/bin/bash
# to_bowang.sh : fresh boot (to_xinye.sh), talk to the officers in the Xinye hall, answer the save prompt No and
# the plan choice with the default, play into the Bowang battle until the first player phase; saves
# sstates/s11_xinye_roam.sav and sstates/s11_bowang_player.sav (~6 min). Check with hshot.sh.
D=$(cd "$(dirname "$0")" && pwd); R="$D/../.."; P="$D/hpress.sh"; PY="$R/.venv/bin/python"
"$D/to_xinye.sh"
"$PY" "$D/untalk.py" 30 >/dev/null
"$D/hsave.sh" "$R/sstates/s11_xinye_roam.sav"
for d in Right Right Right Right Right Right Right Right Right Right Up Up Up Down Down Down Left Left Left; do
  "$P" /dev/null $d X w; "$PY" "$D/untalk.py" 30 >/dev/null
done
for i in $(seq 1 46); do "$P" /dev/null X w w; done
"$D/hsave.sh" "$R/sstates/s11_bowang_player.sav"
