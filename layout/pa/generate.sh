#!/usr/bin/env bash
# Regenerate layout/pa/sg13g2_pa.gds and layout/pa/provenance.json from the
# committed netlist (design/netlist/sg13g2-pa.spice).
#
#   layout/pa/generate.sh           write the GDS and the provenance file
#   layout/pa/generate.sh --check   regenerate to a temp dir; exit 0 only if the
#                                   committed GDS bytes and provenance still
#                                   match and the netlist hash is current
#
# Needs the pinned SG13G2 PDK (`source sim/env.sh` sets PDK_ROOT/PDK) and
# network access for uvx the first time. klt runs through a throwaway uvx
# environment, never a host install.
#
# What it draws: one PDK `npn13G2` cell per PA core device in the netlist
# (XQ<n>, via `klt gen bjt_array`), placed 2 rows x N/2 columns. It draws no
# routing, no bias device (XQref), no resistor, no capacitor and no inductor.
# See layout/README.md.
set -euo pipefail

KLT_PIN="0.9.1"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

mode=write
[[ "${1:-}" == "--check" ]] && mode=check

NETLIST="design/netlist/sg13g2-pa.spice"
GDS="layout/pa/sg13g2_pa.gds"
PROV="layout/pa/provenance.json"
SELF="layout/pa/generate.sh"

# shellcheck source=/dev/null
source sim/env.sh >/dev/null

# PA core devices: XQ<digits> instances of npn13G2 (not XQref, the bias diode).
n_dev="$(grep -cE '^XQ[0-9]+ .* npn13G2( |$)' "$NETLIST")"
if (( n_dev < 2 || n_dev % 2 != 0 )); then
  echo "generate.sh: expected an even number (>=2) of XQ<n> npn13G2 devices, found $n_dev" >&2
  exit 1
fi
rows=2
cols=$(( n_dev / 2 ))

out="$ROOT/${GDS}"
prov_out="$ROOT/${PROV}"
if [[ $mode == check ]]; then
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  out="$tmp/sg13g2_pa.gds"; prov_out="$tmp/provenance.json"
fi

klt() { uvx --from "klayout-tools==${KLT_PIN}" klt "$@"; }

report="$(mktemp)"; trap 'rm -f "$report"' EXIT
klt gen bjt_array --params "{\"rows\": ${rows}, \"cols\": ${cols}}" \
    --cell-name sg13g2_pa -o "$out" --format json > "$report"

python3 -I - "$report" "$out" "$prov_out" "$NETLIST" "$SELF" \
    "$KLT_PIN" "$n_dev" "$rows" "$cols" <<'PY'
import hashlib, json, os, sys
report, gds, prov, netlist, script, pin, n, rows, cols = sys.argv[1:]
sha = lambda p: "sha256:" + hashlib.sha256(open(p, "rb").read()).hexdigest()
r = json.load(open(report))
rec = {
    "schema_version": 1,
    "description": "Provenance of layout/pa/sg13g2_pa.gds (T1 item 2). Placement of PDK npn13G2 cells only; unrouted. See layout/README.md.",
    "netlist": {"path": netlist, "content_hash": sha(netlist)},
    "generator": {
        "script": script,
        "script_content_hash": sha(script),
        "note": "A commit id cannot name the commit that contains its own provenance file; the script's content hash is recorded instead.",
    },
    "klt": {"pin": pin, "run_as": f"uvx --from klayout-tools=={pin} klt gen bjt_array"},
    "pdk": r.get("pdk"),
    "params": {"generator": "bjt_array", "rows": int(rows), "cols": int(cols), "cell_name": "sg13g2_pa"},
    "devices_placed": int(n),
    "gds": {"path": "layout/pa/sg13g2_pa.gds", "content_hash": sha(gds), "bbox_um": r.get("bbox_um")},
    "generator_notes": [n.replace(os.environ["PDK_ROOT"], "$PDK_ROOT") for n in r.get("drc_hints", {}).get("notes", [])],
    "reproducibility": "Byte-identical on regeneration (layout/pa/generate.sh --check compares GDS bytes).",
}
json.dump(rec, open(prov, "w"), indent=2); open(prov, "a").write("\n")
PY

if [[ $mode == check ]]; then
  cmp -s "$out" "$ROOT/$GDS" || { echo "STALE: regenerated GDS bytes differ from $GDS" >&2; exit 1; }
  cmp -s "$prov_out" "$ROOT/$PROV" || { echo "STALE: regenerated provenance differs from $PROV (netlist, generator or pin changed)" >&2; exit 1; }
  echo "layout/pa is fresh (GDS bytes and provenance reproduce)."
else
  echo "wrote $GDS and $PROV"
fi
