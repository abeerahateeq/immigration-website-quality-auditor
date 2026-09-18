#!/usr/bin/env bash
# Starts the 6 local fixture sites on ports 8001-8006 in the background.
set -e
cd "$(dirname "$0")/sample_data"
i=8001
for d in test_site poor_site mid_site thin_site premier_site regional_site; do
  (cd "$d" && python3 -m http.server $i >/dev/null 2>&1 &)
  echo "  $d -> http://127.0.0.1:$i/"
  i=$((i+1))
done
sleep 1
echo "Fixture servers running. Stop them later with: pkill -f http.server"
