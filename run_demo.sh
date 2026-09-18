#!/usr/bin/env bash
# Starts the 6 local mock sites, runs the audit, stops the servers.
set -e
cd "$(dirname "$0")"
p=8001
for d in test_site poor_site mid_site thin_site premier_site regional_site; do
  (cd sample_data/$d && python3 -m http.server $p >/dev/null 2>&1 &)
  p=$((p+1))
done
sleep 2
python3 main.py --input demo_sites.csv --outdir demo_output
pkill -f "http.server 800" || true
echo "Reports: demo_output/report.md and demo_output/report.html"
