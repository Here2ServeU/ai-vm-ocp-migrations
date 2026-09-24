"""
Migration Copilot - OpenShift + Migration Toolkit for Virtualization (MTV) tools.

Tools:
  create_migration_plan  -> drafts an MTV Plan (dry run by default, nothing changes)
  start_migration        -> starts a Plan ONLY when an authorized approver says yes (audited)
  migration_status       -> progress of a Plan, in plain terms
  list_openshift_vms     -> VMs already running on OpenShift Virtualization

Credentials come from a watsonx Orchestrate key-value connection, app_id "openshift":
  api_url               https://api.<cluster>:6443
  token                 service-account token (scoped RBAC, see README)
  ca_cert               optional PEM of the API server CA
  mtv_namespace         default: openshift-mtv
  source_provider       MTV vSphere provider name
  destination_provider  default: host
  network_map           MTV NetworkMap name
  storage_map           MTV StorageMap name
  approvers             optional comma-separated names allowed to approve migrations
                        (default: AUTHORIZED_APPROVERS below)
If no connection is found, the tools run in DEMO MODE and change nothing.
"""

import datetime as dt
import logging
import tempfile
from typing import List, Optional

import yaml
from ibm_watsonx_orchestrate.agent_builder.connections import (
    ConnectionType,
    ExpectedCredentials,
)
from ibm_watsonx_orchestrate.agent_builder.tools import ToolPermission, tool

log = logging.getLogger("copilot.openshift")
APP_ID = "openshift"
CREDS = [ExpectedCredentials(app_id=APP_ID, type=ConnectionType.KEY_VALUE)]
GROUP, VERSION = "forklift.konveyor.io", "v1beta1"

# Only these people may approve a migration. Override with the "approvers" connection key.
AUTHORIZED_APPROVERS = ("Emmanuel Naweji",)

_DEMO_RUNS: dict = {}  # demo mode only: plan name -> simulated progress


# ---------- helpers ----------


def _settings() -> Optional[dict]:
    try:
        from ibm_watsonx_orchestrate.run import connections

        kv = connections.key_value(APP_ID)
        if kv and kv.get("api_url") and kv.get("token"):
            return dict(kv)
    except (Exception, SystemExit) as exc:  # no connection -> demo mode
        log.info("openshift connection not available (%s); demo mode", exc)
    return None


def _api(s: dict):
    from kubernetes import client

    cfg = client.Configuration()
    cfg.host = s["api_url"]
    cfg.api_key = {"authorization": "Bearer " + s["token"]}
    if s.get("ca_cert"):
        f = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
        f.write(s["ca_cert"])
        f.close()
        cfg.ssl_ca_cert = f.name
    return client.ApiClient(cfg)


def _ns(s: Optional[dict]) -> str:
    return (s or {}).get("mtv_namespace", "openshift-mtv")


def _plan_body(s: Optional[dict], name: str, vm_ids: List[str], target_ns: str, warm: bool) -> dict:
    s = s or {}
    ns = _ns(s)

    def ref(key: str, default: str) -> dict:
        return {"name": s.get(key, default), "namespace": ns}

    return {
        "apiVersion": f"{GROUP}/{VERSION}",
        "kind": "Plan",
        "metadata": {"name": name, "namespace": ns, "labels": {"created-by": "migration-copilot"}},
        "spec": {
            "warm": warm,
            "targetNamespace": target_ns,
            "provider": {
                "source": ref("source_provider", "vsphere"),
                "destination": ref("destination_provider", "host"),
            },
            "map": {
                "network": ref("network_map", "vsphere-network-map"),
                "storage": ref("storage_map", "vsphere-storage-map"),
            },
            "vms": [{"id": i} for i in vm_ids],
        },
    }


def _approvers(s: Optional[dict]) -> List[str]:
    names = (s or {}).get("approvers", "")
    return [n.strip() for n in names.split(",") if n.strip()] or list(AUTHORIZED_APPROVERS)


def _same_name(a: str, b: str) -> bool:
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


def _audit(event: str, **fields):
    """Structured audit line. Ship tool logs to your SIEM for a durable record."""
    log.warning("AUDIT %s %s", event, {"at": dt.datetime.now(dt.UTC).isoformat(), **fields})


# ---------- tools ----------


@tool(permission=ToolPermission.READ_WRITE, expected_credentials=CREDS)
def create_migration_plan(
    plan_name: str, vm_ids: List[str], target_namespace: str, warm: bool = False, dry_run: bool = True
) -> dict:
    """
    Draft a Migration Toolkit for Virtualization (MTV) plan that moves VMware VMs to
    OpenShift Virtualization. By default this is a dry run and changes nothing.

    :param plan_name: Lowercase name for the plan, for example "finance-wave-1".
    :param vm_ids: vSphere VM ids from discover_vms, for example ["vm-101", "vm-103"].
    :param target_namespace: OpenShift project the migrated VMs will run in.
    :param warm: True for warm migration (copies data while the VM runs; shorter downtime).
    :param dry_run: True returns the plan YAML only. False saves the plan in the cluster
                    (it still does not move anything until start_migration is approved).
    :returns: The plan YAML and whether it was saved.
    """
    s = _settings()
    body = _plan_body(s, plan_name, vm_ids, target_namespace, warm)
    saved = False
    if not dry_run and s:
        from kubernetes import client

        client.CustomObjectsApi(_api(s)).create_namespaced_custom_object(
            GROUP, VERSION, _ns(s), "plans", body
        )
        saved = True
        _audit("plan_created", plan=plan_name, vms=vm_ids, target=target_namespace)
    return {
        "mode": "live" if s else "demo",
        "saved": saved,
        "vm_count": len(vm_ids),
        "plan_yaml": yaml.safe_dump(body, sort_keys=False),
    }


@tool(permission=ToolPermission.READ_WRITE, expected_credentials=CREDS)
def start_migration(
    plan_name: str, approver_name: str, approval_confirmed: bool, change_ticket: Optional[str] = None
) -> dict:
    """
    Start an MTV migration plan. Only call this after an authorized approver has reviewed
    the plan and explicitly approved it in the conversation.

    :param plan_name: The saved plan to run.
    :param approver_name: Full name of the person who approved this migration. Must be an
                          authorized approver, for example "Emmanuel Naweji".
    :param approval_confirmed: Must be true, meaning the approver explicitly said yes.
    :param change_ticket: Optional change or ticket number for the audit record.
    :returns: Whether the migration started, plus the audit details recorded.
    """
    s = _settings()
    allowed = _approvers(s)
    if not approval_confirmed or not approver_name.strip():
        return {
            "started": False,
            "reason": "A named approver must explicitly approve before a migration starts.",
            "authorized_approvers": allowed,
        }
    approver = next((a for a in allowed if _same_name(approver_name, a)), None)
    if approver is None:
        _audit("migration_rejected", plan=plan_name, approver=approver_name, reason="not authorized")
        return {
            "started": False,
            "reason": f"{approver_name} is not authorized to approve migrations.",
            "authorized_approvers": allowed,
        }
    stamp = dt.datetime.now(dt.UTC).isoformat()
    audit = {
        "plan": plan_name,
        "approved_by": approver,
        "change_ticket": change_ticket or "none",
        "approved_at": stamp,
    }
    if s:
        from kubernetes import client

        body = {
            "apiVersion": f"{GROUP}/{VERSION}",
            "kind": "Migration",
            "metadata": {
                "generateName": f"{plan_name}-",
                "namespace": _ns(s),
                "annotations": {f"copilot/{k}": v for k, v in audit.items()},
            },
            "spec": {"plan": {"name": plan_name, "namespace": _ns(s)}},
        }
        client.CustomObjectsApi(_api(s)).create_namespaced_custom_object(
            GROUP, VERSION, _ns(s), "migrations", body
        )
    else:
        _DEMO_RUNS[plan_name] = 0
    _audit("migration_started", **audit)
    return {"started": True, "mode": "live" if s else "demo", "audit": audit}


@tool(permission=ToolPermission.READ_ONLY, expected_credentials=CREDS)
def migration_status(plan_name: str) -> dict:
    """
    Show the progress of an MTV migration plan, per VM.

    :param plan_name: The plan to check.
    :returns: Overall state and, for each VM, its current step and percent complete.
    """
    s = _settings()
    if not s:
        pct = min(100, _DEMO_RUNS.get(plan_name, 0) + 35)
        _DEMO_RUNS[plan_name] = pct
        step = "Completed" if pct >= 100 else "DiskTransfer"
        return {
            "mode": "demo",
            "plan": plan_name,
            "state": "Succeeded" if pct >= 100 else "Executing",
            "vms": [{"vm": "demo-vm", "step": step, "percent": pct}],
        }

    from kubernetes import client

    plan = client.CustomObjectsApi(_api(s)).get_namespaced_custom_object(
        GROUP, VERSION, _ns(s), "plans", plan_name
    )
    status = plan.get("status", {})
    conds = [c["type"] for c in status.get("conditions", []) if c.get("status") == "True"]
    state = next((c for c in ("Failed", "Succeeded", "Executing", "Ready") if c in conds), "Pending")
    vms = []
    for vm in status.get("migration", {}).get("vms", []):
        steps = vm.get("pipeline", [])
        current = next((p for p in steps if p.get("phase") == "Running"), steps[-1] if steps else {})
        prog = current.get("progress", {})
        pct = round(100 * prog.get("completed", 0) / prog["total"]) if prog.get("total") else None
        vms.append(
            {
                "vm": vm.get("name") or vm.get("id"),
                "phase": vm.get("phase"),
                "step": current.get("name"),
                "percent": pct,
                "error": (vm.get("error") or {}).get("reasons"),
            }
        )
    return {"mode": "live", "plan": plan_name, "state": state, "vms": vms}


@tool(permission=ToolPermission.READ_ONLY, expected_credentials=CREDS)
def list_openshift_vms(namespace: str) -> dict:
    """
    List virtual machines running on OpenShift Virtualization in one project.

    :param namespace: The OpenShift project to look in.
    :returns: Each VM's name and status (for example Running or Stopped).
    """
    s = _settings()
    if not s:
        return {"mode": "demo", "namespace": namespace, "vms": [{"name": "fin-web-01", "status": "Running"}]}
    from kubernetes import client

    res = client.CustomObjectsApi(_api(s)).list_namespaced_custom_object(
        "kubevirt.io", "v1", namespace, "virtualmachines"
    )
    return {
        "mode": "live",
        "namespace": namespace,
        "vms": [
            {"name": i["metadata"]["name"], "status": i.get("status", {}).get("printableStatus", "Unknown")}
            for i in res.get("items", [])
        ],
    }
