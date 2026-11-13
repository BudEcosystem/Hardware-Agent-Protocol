#!/bin/sh
# Copy the portable C library into the self-contained Arduino library layout.
# Arduino libraries cannot reference files outside their folder, so src/ holds
# copies; `sync_arduino.sh --check` (run by ctest) fails when they drift.
# protocol/serial/frame.{c,h} are copied byte-for-byte from the repository's
# framing layer, never modified.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
root=$(cd "$here/../.." && pwd)
dst="$here/arduino/BHMS/src"
mode=${1:-sync}
status=0
for f in "$here/include/bhms.h" "$here/include/bhms_config.h" "$here/include/bhms_hal.h" \
         "$here/src/bhms_codec.c" "$here/src/bhms_tx.c" "$here/src/bhms_endpoint.c" \
         "$root/protocol/serial/frame.c" "$root/protocol/serial/frame.h"; do
    if [ "$mode" = "--check" ]; then
        cmp -s "$f" "$dst/$(basename "$f")" || { echo "out of sync: $(basename "$f")" >&2; status=1; }
    else
        cp "$f" "$dst/"
    fi
done
exit $status
