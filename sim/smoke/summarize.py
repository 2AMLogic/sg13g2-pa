#!/usr/bin/env python3
"""Render a smoke record (Markdown) from klt sim reports.

Usage: summarize.py <record-id> <git-sha> <dirty:0|1> <klt-version> <ngspice-banner>
                    <provenance.json> <out-dir> <report-name>...

Reads <out-dir>/<report-name>.report.json for each name, plus the
PDK provenance JSON sim_require_pdk produced. Prints the record on stdout.
Exit 1 if any report is missing or any corner is not `pass`.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from provenance import commit_line, sha  # noqa: E402


def main(argv):
    rid, git_sha, dirty, klt_ver, ng_banner, prov_path, out_dir = argv[1:8]
    names = argv[8:]
    smoke_dir = os.path.dirname(os.path.abspath(__file__))
    prov = json.load(open(prov_path))
    ok = True
    lines = [
        f"# Toolchain smoke record {rid}",
        "",
        "**This is a toolchain smoke test, not a design result.** It shows that the pinned",
        "PDK, the OSDI models and `klt sim` run together. The npn13G2 operating point is at",
        "the typical HBT corner **only**; the spec's corner box (HBT corners, supply,",
        "temperature) is issue #2's, and nothing here is evidence about it. All figures",
        "below are **simulated** (ngspice, `klt sim`), at the corner named on each row.",
        "",
        "## Provenance",
        "",
        f"- UTC timestamp / record id: `{rid}`",
        commit_line(git_sha, dirty),
        f"- PDK: IHP-Open-PDK, pinned `{prov['pinned_release_tag']}`; installed release "
        f"`{prov['installed_release_raw']}` (identity route `{prov['identity_route']}`, "
        f"`.fetched-version` value `{prov['installed_release_raw']}`); verified against `sim/pdk.json`",
        f"- `klt`: `{klt_ver}`",
        f"- Local ngspice: `{ng_banner}` (runs the single-unit npn13G2 op; too old to load the OSDI "
        "objects, which target OSDI 0.4)",
        "",
        "### OSDI objects and model inputs (sha256)",
        "",
    ]
    for f in prov["model_inputs"]:
        lines.append(f"- `{f['path']}` `{f['sha256']}`")
    lines += ["", "### Decks and requests (sha256)", ""]
    for fn in sorted(os.listdir(smoke_dir)):
        if fn.endswith((".spice", ".request.json")):
            lines.append(f"- `sim/smoke/{fn}` `{sha(os.path.join(smoke_dir, fn))}`")
    lines += ["", "## Results", ""]
    for name in names:
        rp = os.path.join(out_dir, f"{name}.report.json")
        if not os.path.isfile(rp):
            lines += [f"### {name}", "", "**No report produced.**", ""]
            ok = False
            continue
        try:
            r = json.load(open(rp))
        except ValueError:
            lines += [f"### {name}", "", "**No usable report** (the `klt sim` run failed; see its stderr).", ""]
            ok = False
            continue
        env = r.get("environment", {})
        rem = env.get("remote") or {}
        lines += [f"### {name}", ""]
        lines.append(f"- status: **{r.get('status')}** ({r.get('passed')} pass / {r.get('failed')} fail / "
                     f"{r.get('errored')} error of {r.get('corner_count')})")
        where = "batch fleet worker" if rem else "local host"
        lines.append(f"- ran on: {where}; ngspice major version `{env.get('engine_version')}`")
        if rem:
            lines.append(f"- batch job id: `{rem.get('job_id')}` (state `{rem.get('state')}`, "
                         f"`{rem.get('instance_type')}` {rem.get('lifecycle')})")
        lines.append("")
        meas = [m["name"] for m in r["corners"][0]["measurements"]]
        lines.append("| corner | status | " + " | ".join(meas) + " |")
        lines.append("|---|---|" + "---|" * len(meas))
        for c in r["corners"]:
            vals = " | ".join("%.6g" % m["value"] if m["value"] is not None else "n/a"
                              for m in c["measurements"])
            lines.append(f"| `{c['corner_id']}` | {c['status']} | {vals} |")
            if c["status"] != "pass":
                ok = False
        lines.append("")
    lines += [
        "## Statement",
        "",
        "- Toolchain smoke test only; no claim about any PA figure of merit.",
        "- HBT: `hbt_typ` corner only. The npn13G2 point (Vbe 0.80 V, Vce 1.0 V, Nx=1) is inside the "
        "model card's stated validity window (ic < 3 mA, vbe 0.65-0.96 V, vce 0.4-2.0 V); breakdown "
        "and VBIC-validity checks for the PA are out of scope here.",
        "- MOS: core (LV) `sg13_lv_nmos` / `sg13_lv_pmos`, minimum size, five corners tt/ff/ss/fs/sf, "
        "VDD 1.2 V, 27 C, fixed 10 fF load.",
        "- The corner box for the PA belongs to the spec (#2).",
        "",
    ]
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
