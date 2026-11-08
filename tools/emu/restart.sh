#!/bin/bash
# restart.sh [state.sav] : stop this project's emulator and boot the English build (optionally from a state)
D=$(cd "$(dirname "$0")" && pwd); R="$D/../.."
"$D/headless.sh" stop; timeout 2 tail -f /dev/null
"$D/headless.sh" "$R/build/sangokushi_koumeiden_en.cue" ${1:+"$1"}
for i in $(seq 1 30); do [ -S "$XDG_RUNTIME_DIR/skm-vpad.sock" ] && break; timeout 0.5 tail -f /dev/null; done
timeout ${WAIT:-10} tail -f /dev/null
