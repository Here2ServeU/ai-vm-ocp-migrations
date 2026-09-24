"""
Migration Copilot - VMware vCenter tools (READ-ONLY).

Tools:
  discover_vms       -> list VMs with size, OS and migration readiness
  readiness_summary  -> counts by readiness group, for leadership questions

Credentials come from a watsonx Orchestrate connection with app_id "vcenter"
(basic auth: url = vCenter host, username, password).
If no connection is found, the tools run in DEMO MODE with sample data,
so you can present safely without touching a real environment.
"""

import logging
import ssl
from typing import Optional

from ibm_watsonx_orchestrate.agent_builder.connections import (
    ConnectionType,
    ExpectedCredentials,
)
from ibm_watsonx_orchestrate.agent_builder.tools import ToolPermission, tool

log = logging.getLogger("copilot.vcenter")
APP_ID = "vcenter"
CREDS = [ExpectedCredentials(app_id=APP_ID, type=ConnectionType.BASIC_AUTH)]

# Sizes above these values need extra planning time.
LARGE_DISK_GB = 2048
LARGE_CPU = 16
LARGE_MEM_GB = 128

# Sample estate for demos. Replace freely; names are fictional.
SAMPLE_VMS = [
    {
        "id": "vm-101",
        "name": "fin-web-01",
        "cluster": "finance",
        "power_state": "poweredOn",
        "guest_os": "Red Hat Enterprise Linux 9 (64-bit)",
        "cpus": 2,
        "memory_gb": 8,
        "disks": [{"size_gb": 60, "rdm": False, "shared": False}],
        "has_snapshots": False,
        "passthrough": False,
    },
    {
        "id": "vm-102",
        "name": "fin-web-02",
        "cluster": "finance",
        "power_state": "poweredOn",
        "guest_os": "Red Hat Enterprise Linux 9 (64-bit)",
        "cpus": 2,
        "memory_gb": 8,
        "disks": [{"size_gb": 60, "rdm": False, "shared": False}],
        "has_snapshots": True,
        "passthrough": False,
    },
    {
        "id": "vm-103",
        "name": "fin-app-01",
        "cluster": "finance",
        "power_state": "poweredOn",
        "guest_os": "Microsoft Windows Server 2019 (64-bit)",
        "cpus": 4,
        "memory_gb": 16,
        "disks": [{"size_gb": 120, "rdm": False, "shared": False}],
        "has_snapshots": False,
        "passthrough": False,
    },
    {
        "id": "vm-104",
        "name": "fin-db-01",
        "cluster": "finance",
        "power_state": "poweredOn",
        "guest_os": "Red Hat Enterprise Linux 8 (64-bit)",
        "cpus": 16,
        "memory_gb": 128,
        "disks": [
            {"size_gb": 200, "rdm": False, "shared": False},
            {"size_gb": 2500, "rdm": True, "shared": False},
        ],
        "has_snapshots": False,
        "passthrough": False,
    },
    {
        "id": "vm-105",
        "name": "hr-portal-01",
        "cluster": "hr",
        "power_state": "poweredOn",
        "guest_os": "Microsoft Windows Server 2022 (64-bit)",
        "cpus": 4,
        "memory_gb": 16,
        "disks": [{"size_gb": 100, "rdm": False, "shared": False}],
        "has_snapshots": False,
        "passthrough": False,
    },
    {
        "id": "vm-106",
        "name": "hr-legacy-01",
        "cluster": "hr",
        "power_state": "poweredOff",
        "guest_os": "Microsoft Windows Server 2008 R2 (64-bit)",
        "cpus": 2,
        "memory_gb": 4,
        "disks": [{"size_gb": 80, "rdm": False, "shared": False}],
        "has_snapshots": True,
        "passthrough": False,
    },
    {
        "id": "vm-107",
        "name": "ops-monitor-01",
        "cluster": "ops",
        "power_state": "poweredOn",
        "guest_os": "Red Hat Enterprise Linux 9 (64-bit)",
        "cpus": 4,
        "memory_gb": 8,
        "disks": [{"size_gb": 40, "rdm": False, "shared": False}],
        "has_snapshots": False,
        "passthrough": False,
    },
    {
        "id": "vm-108",
        "name": "ops-gpu-01",
        "cluster": "ops",
        "power_state": "poweredOn",
        "guest_os": "Ubuntu Linux (64-bit)",
        "cpus": 8,
        "memory_gb": 64,
        "disks": [{"size_gb": 500, "rdm": False, "shared": False}],
        "has_snapshots": False,
        "passthrough": True,
    },
]

# Guest OS families that usually migrate cleanly. Always confirm against
# Red Hat's current supported guest OS list for OpenShift Virtualization.
LIKELY_SUPPORTED = (
    "red hat enterprise linux 8",
    "red hat enterprise linux 9",
    "windows server 2016",
    "windows server 2019",
    "windows server 2022",
    "windows server 2025",
    "ubuntu",
    "centos stream",
)


# ---------- helpers ----------


def _vcenter_creds():
    """Return Orchestrate basic-auth credentials, or None for demo mode."""
    try:
        from ibm_watsonx_orchestrate.run import connections

        c = connections.basic_auth(APP_ID)
        if c and c.url and c.username:
            return c
    except (Exception, SystemExit) as exc:  # no connection -> demo mode
        log.info("vcenter connection not available (%s); using demo data", exc)
    return None


def _live_vms(creds) -> list:
    """Read VMs from vCenter with pyVmomi. Read-only calls only."""
    from pyVim.connect import Disconnect, SmartConnect
    from pyVmomi import vim

    host = creds.url.replace("https://", "").replace("http://", "").rstrip("/")
    ctx = ssl.create_default_context()
    if creds.server_cert:
        ctx.load_verify_locations(cadata=creds.server_cert)
    si = SmartConnect(host=host, user=creds.username, pwd=creds.password, sslContext=ctx)
    try:
        content = si.RetrieveContent()
        view = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
        out = []
        for vm in view.view:
            cfg = vm.config
            if cfg is None or cfg.template:
                continue
            disks, passthrough = [], False
            for dev in cfg.hardware.device:
                if isinstance(dev, vim.vm.device.VirtualDisk):
                    b = dev.backing
                    disks.append(
                        {
                            "size_gb": round(dev.capacityInKB / 1024 / 1024, 1),
                            "rdm": isinstance(b, vim.vm.device.VirtualDisk.RawDiskMappingVer1BackingInfo),
                            "shared": getattr(b, "sharing", "") == "sharingMultiWriter",
                        }
                    )
                if isinstance(dev, vim.vm.device.VirtualPCIPassthrough):
                    passthrough = True
            host_obj = vm.runtime.host
            out.append(
                {
                    "id": vm._moId,
                    "name": vm.name,
                    "cluster": host_obj.parent.name if host_obj else "unknown",
                    "power_state": str(vm.runtime.powerState),
                    "guest_os": cfg.guestFullName or "unknown",
                    "cpus": cfg.hardware.numCPU,
                    "memory_gb": round(cfg.hardware.memoryMB / 1024, 1),
                    "disks": disks,
                    "has_snapshots": vm.snapshot is not None,
                    "passthrough": passthrough,
                }
            )
        view.Destroy()
        return out
    finally:
        Disconnect(si)


def assess(vm: dict) -> dict:
    """Add readiness, blockers and prep steps to one VM record."""
    blockers, prep = [], []
    total_disk = sum(d["size_gb"] for d in vm["disks"])
    os_name = vm["guest_os"].lower()

    if any(d["rdm"] for d in vm["disks"]):
        blockers.append("Uses a raw device mapping (RDM) disk")
    if any(d["shared"] for d in vm["disks"]):
        blockers.append("Uses a shared multi-writer disk (clustered app)")
    if vm["passthrough"]:
        blockers.append("Uses PCI passthrough hardware (for example a GPU)")
    if not any(k in os_name for k in LIKELY_SUPPORTED):
        blockers.append(f"Guest OS needs review: {vm['guest_os']}")

    if vm["has_snapshots"]:
        prep.append("Remove or consolidate snapshots before migrating")
    if total_disk > LARGE_DISK_GB:
        prep.append("Large disks: plan a warm migration and a longer window")
    if vm["cpus"] > LARGE_CPU or vm["memory_gb"] > LARGE_MEM_GB:
        prep.append("Large VM: confirm target node capacity")

    if vm["power_state"] != "poweredOn":
        readiness = "Retire candidate"
    elif blockers:
        readiness = "Blocked"
    elif prep:
        readiness = "Ready with prep"
    else:
        readiness = "Ready"

    risk = min(100, 25 * len(blockers) + 10 * len(prep))
    return {
        **vm,
        "total_disk_gb": total_disk,
        "readiness": readiness,
        "risk_score": risk,
        "blockers": blockers,
        "prep_steps": prep,
    }


def load_assessed(cluster: Optional[str] = None) -> tuple:
    creds = _vcenter_creds()
    vms = _live_vms(creds) if creds else SAMPLE_VMS
    if cluster:
        vms = [v for v in vms if v["cluster"].lower() == cluster.lower()]
    return [assess(v) for v in vms], ("live" if creds else "demo")


# ---------- tools the agent can call ----------


@tool(permission=ToolPermission.READ_ONLY, expected_credentials=CREDS)
def discover_vms(cluster: Optional[str] = None, readiness: Optional[str] = None) -> dict:
    """
    List VMware virtual machines with size, operating system and migration readiness
    for moving to OpenShift Virtualization.

    :param cluster: Optional vSphere cluster name to filter by, for example "finance".
    :param readiness: Optional filter: "Ready", "Ready with prep", "Blocked" or "Retire candidate".
    :returns: A dict with "mode" (live or demo) and "vms", a list of VM records sorted
              from lowest to highest risk. Each record has name, id, guest_os, cpus,
              memory_gb, total_disk_gb, readiness, risk_score, blockers and prep_steps.
    """
    vms, mode = load_assessed(cluster)
    if readiness:
        vms = [v for v in vms if v["readiness"].lower() == readiness.lower()]
    vms.sort(key=lambda v: (v["risk_score"], v["total_disk_gb"]))
    for v in vms:
        v.pop("disks", None)  # keep responses small for the model
    return {"mode": mode, "count": len(vms), "vms": vms}


@tool(permission=ToolPermission.READ_ONLY, expected_credentials=CREDS)
def readiness_summary(cluster: Optional[str] = None) -> dict:
    """
    Summarize how many VMs are ready to migrate to OpenShift Virtualization.

    :param cluster: Optional vSphere cluster name to filter by.
    :returns: Counts per readiness group, total vCPU, memory and disk,
              and the most common blockers.
    """
    vms, mode = load_assessed(cluster)
    groups, blockers = {}, {}
    for v in vms:
        groups[v["readiness"]] = groups.get(v["readiness"], 0) + 1
        for b in v["blockers"]:
            key = b.split(":")[0]
            blockers[key] = blockers.get(key, 0) + 1
    return {
        "mode": mode,
        "total_vms": len(vms),
        "by_readiness": groups,
        "total_vcpu": sum(v["cpus"] for v in vms),
        "total_memory_gb": sum(v["memory_gb"] for v in vms),
        "total_disk_gb": round(sum(v["total_disk_gb"] for v in vms), 1),
        "top_blockers": sorted(blockers.items(), key=lambda kv: -kv[1]),
    }
