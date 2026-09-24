"""Rehearse the demo on your laptop, no Orchestrate or clusters needed.
Run:  python demo_local.py
"""

import json
import sys

sys.path.insert(0, "tools")
import openshift_tools as ocp  # noqa: E402
from vcenter_tools import load_assessed  # noqa: E402

vms, mode = load_assessed("finance")
print(f"[{mode} mode] finance cluster\n")
print(f"{'VM':<14}{'Readiness':<18}{'Risk':>5}  Notes")
for v in sorted(vms, key=lambda v: v["risk_score"]):
    notes = "; ".join(v["blockers"] + v["prep_steps"]) or "-"
    print(f"{v['name']:<14}{v['readiness']:<18}{v['risk_score']:>5}  {notes}")

wave = [v["id"] for v in vms if v["readiness"] in ("Ready", "Ready with prep")]
plan = ocp._plan_body(None, "finance-wave-1", wave, "finance-prod", warm=False)
print("\nDraft MTV plan (dry run):\n")
print(json.dumps(plan["spec"], indent=2))
