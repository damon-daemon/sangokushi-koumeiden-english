#!/bin/bash
# to_xinye.sh : boot the English build fresh (states hold the old program), NEW GAME, skip the prologue,
# through the Xuchang talk to the Xinye council hall (Liu Bei's first line on screen); saves
# sstates/s10_choice.sav (~2.5 min). Timing-sensitive: check with hshot.sh.
D=$(cd "$(dirname "$0")" && pwd); R="$D/../.."; P="$D/hpress.sh"
WAIT=30 "$D/restart.sh"
"$P" /dev/null Return w w w Return w w w Up X w w w w   # Up: the memory card holds a save (session 14), so the cursor starts on CONTINUE
"$D/hsave.sh" "$R/sstates/s10_choice.sav"
"$P" /dev/null Down w X w w w w w w w
for i in $(seq 1 12); do "$P" /dev/null X w w; done
"$P" /dev/null w w w w w w w w
for i in $(seq 1 3); do "$P" /dev/null X w; done
"$P" /dev/null X w w w w w w w w w
for i in $(seq 1 3); do "$P" /dev/null X w; done
