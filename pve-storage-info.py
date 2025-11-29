#!/usr/bin/env python3
# BSD 2-Clause License
#
# Copyright (c) 2025, xoppepop
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from ipaddress import ip_address, AddressValueError

__version__ = "0.1.0b1"

def run_pvesh(args_list):
    result = subprocess.run(
        ["pvesh"] + args_list,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def parse_size_to_mb(size_str):
    if not size_str:
        return None
    unit = size_str[-1]
    num_str = size_str[:-1]
    if unit.isdigit():
        try:
            return int(size_str)
        except ValueError:
            return None
    if "." in num_str:
        num_str = num_str.split(".", 1)[0]
    try:
        num = int(num_str)
    except ValueError:
        return None
    unit = unit.upper()
    if unit == "K":
        return num // 1024
    if unit == "M":
        return num
    if unit == "G":
        return num * 1024
    if unit == "T":
        return num * 1024 * 1024
    return num


def humanize_mb(mb):
    try:
        mb = int(mb)
    except (TypeError, ValueError):
        return str(mb)
    if mb >= 1024 * 1024:
        val = mb / (1024 * 1024)
        unit = "TiB"
    elif mb >= 1024:
        val = mb / 1024
        unit = "GiB"
    else:
        val = mb
        unit = "MiB"
    return f"{mb} ({val:.2f} {unit})"


def is_mb_column(col_name):
    return col_name.lower().endswith("mb")


def print_table(headers, rows, human=False):
    str_rows = []
    for row in rows:
        line = []
        for col in headers:
            val = row.get(col, "")
            if human and is_mb_column(col) and isinstance(val, (int, float)):
                val_str = humanize_mb(val)
            else:
                val_str = str(val)
            line.append(val_str)
        str_rows.append(line)
    widths = [len(h) for h in headers]
    for line in str_rows:
        for i, cell in enumerate(line):
            widths[i] = max(widths[i], len(cell))
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep_line = "  ".join("-" * widths[i] for i in range(len(headers)))
    print(header_line)
    print(sep_line)
    for line in str_rows:
        print("  ".join(line[i].ljust(widths[i]) for i in range(len(headers))))


def extract_disk_info(cluster_name, node, vmid, vmname, bus, diskspec):
    if ":" not in diskspec:
        return None
    storage, rest = diskspec.split(":", 1)
    vmdisk = rest.split(",", 1)[0]
    pos = diskspec.rfind("size=")
    if pos == -1:
        return None
    size_part = diskspec[pos + 5 :]
    if "," in size_part:
        size = size_part.split(",", 1)[0]
    else:
        size = size_part
    size = size.strip()
    if not size:
        return None
    size_mb = parse_size_to_mb(size)
    if size_mb is None:
        return None
    return {
        "cluster": cluster_name,
        "node": node,
        "vmid": str(vmid),
        "vmname": vmname,
        "storage": storage,
        "vmdisk": vmdisk,
        "size": size,
        "size_mb": size_mb,
    }


def fetch_vm_disks(cluster_name, vm_entry):
    vmid = vm_entry["vmid"]
    node = vm_entry["node"]
    vmname = vm_entry["vmname"]
    vtype = vm_entry["type"]
    try:
        if vtype == "qemu":
            cfg = run_pvesh(
                [
                    "get",
                    f"/nodes/{node}/qemu/{vmid}/config",
                    "--output-format",
                    "json",
                ]
            )
        elif vtype == "lxc":
            cfg = run_pvesh(
                ["get", f"/nodes/{node}/lxc/{vmid}/config", "--output-format", "json"]
            )
        else:
            return []
    except subprocess.CalledProcessError as e:
        sys.stderr.write(
            f"Warning: cannot get config for {vtype} {vmid} on {node}: {e.stderr}\n"
        )
        return []
    if not cfg:
        return []
    rows = []
    for key, value in cfg.items():
        value_str = str(value)
        if vtype == "qemu":
            if not (
                key.startswith("scsi")
                or key.startswith("ide")
                or key.startswith("virtio")
            ):
                continue
            if "media=cdrom" in value_str:
                continue
        elif vtype == "lxc":
            if not (key == "rootfs" or key.startswith("mp")):
                continue
        info = extract_disk_info(cluster_name, node, vmid, vmname, key, value_str)
        if info:
            rows.append(info)
    return rows


def parse_corosync_conf(path="/etc/corosync/corosync.conf"):
    try:
        with open(path, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return None
    except OSError as e:
        sys.stderr.write(f"Warning: cannot read {path}: {e}\n")
        return None
    cluster_name = None
    nodes = {}
    current_node_name = None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("cluster_name:"):
            _, val = stripped.split(":", 1)
            cluster_name = val.strip()
            continue
        if stripped.startswith("name:"):
            _, val = stripped.split(":", 1)
            current_node_name = val.strip()
            continue
        if stripped.startswith("ring0_addr:"):
            _, val = stripped.split(":", 1)
            addr = val.strip()
            if current_node_name:
                nodes[current_node_name] = addr
            continue
    return {
        "cluster_name": cluster_name,
        "nodes": nodes,
    }


def is_private_ip(ip_str):
    try:
        return ip_address(ip_str).is_private
    except (ValueError, AddressValueError):
        return False


def get_node_external_info(node):
    try:
        net_info = run_pvesh(
            ["get", f"/nodes/{node}/network", "--output-format", "json"]
        )
    except subprocess.CalledProcessError as e:
        sys.stderr.write(
            f"Warning: cannot get network info for node {node}: {e.stderr}\n"
        )
        return (None, None, None)
    except Exception as e:
        sys.stderr.write(
            f"Warning: error reading network info for node {node}: {e}\n"
        )
        return (None, None, None)
    if not net_info:
        return (None, None, None)
    best = None
    for iface in net_info:
        if not iface.get("active"):
            continue
        families = iface.get("families") or []
        if "inet" not in families:
            continue
        addr = iface.get("address")
        cidr = iface.get("cidr")
        gw = iface.get("gateway")
        if not addr or not gw:
            continue
        candidate = (addr, cidr, gw)
        if best is None:
            best = candidate
        else:
            best_ip = best[0]
            cand_ip = addr
            if is_private_ip(best_ip) and not is_private_ip(cand_ip):
                best = candidate
    if best is None:
        return (None, None, None)
    return best


def main():
    parser = argparse.ArgumentParser(
        description="Get disk usage and storage info for Proxmox VMs/LXC."
    )
    parser.add_argument(
        "--version",
        help="Prints version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--vmid",
        help="Filter by VMID list (comma-separated), e.g. 100,101,121",
    )
    parser.add_argument(
        "--node",
        help="Filter by node list (comma-separated), e.g. node1,node2",
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="Do not print header line in CSV output",
    )
    parser.add_argument(
        "--total-per-vm",
        action="store_true",
        help="Show total disk consumption per VM (sum of all disks, in MB)",
    )
    parser.add_argument(
        "--total-per-node",
        action="store_true",
        help="Show total disk consumption per node (sum of all VMs, in MB)",
    )
    parser.add_argument(
        "--vm-per-storage",
        action="store_true",
        help="Show per-VM usage per storage (cluster,node,vmid,vmname,storage,size_MB)",
    )
    parser.add_argument(
        "--list-nodes",
        action="store_true",
        help="List all nodes that have VMs/LXC in /cluster/resources",
    )
    parser.add_argument(
        "--list-vmids",
        action="store_true",
        help="List all VMIDs from /cluster/resources",
    )
    parser.add_argument(
        "--list-storages",
        action="store_true",
        help="List storages per node (total/used/available MB and percentages)",
    )
    parser.add_argument(
        "--cluster-info",
        action="store_true",
        help="Show cluster name, node, cluster_ip (ring0_addr) and external IP/gateway info",
    )
    parser.add_argument(
        "--output",
        choices=["table", "csv", "json"],
        default="table",
        help="Output format: table (default), csv or json",
    )
    parser.add_argument(
        "--human",
        action="store_true",
        help="In table mode, show MB fields with human-readable sizes (GiB/TiB)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        help="Number of parallel workers for pvesh calls (default: up to 8)",
    )
    args = parser.parse_args()
    vmid_filter = set()
    if args.vmid:
        vmid_filter = {v.strip() for v in args.vmid.split(",") if v.strip()}
    node_filter = set()
    if args.node:
        node_filter = {n.strip() for n in args.node.split(",") if n.strip()}
    try:
        cluster_status = run_pvesh(
            ["get", "/cluster/status", "--output-format", "json"]
        )
    except subprocess.CalledProcessError as e:
        print(
            "Error running pvesh /cluster/status:",
            e.stderr,
            file=sys.stderr,
        )
        sys.exit(1)
    cluster_name = "standalone"
    if cluster_status:
        for item in cluster_status:
            if item.get("type") == "cluster":
                cluster_name = item.get("name", cluster_name)
                break
    try:
        vm_info = run_pvesh(
            ["get", "/cluster/resources", "--type", "vm", "--output-format", "json"]
        )
    except subprocess.CalledProcessError as e:
        print(
            "Error running pvesh /cluster/resources:",
            e.stderr,
            file=sys.stderr,
        )
        sys.exit(1)
    if not vm_info:
        vm_info = []
    if args.list_nodes:
        nodes = sorted({vm.get("node") for vm in vm_info if vm.get("node")})
        if args.output == "json":
            print(json.dumps(nodes, indent=2))
            return
        if args.output == "csv":
            for n in nodes:
                print(n)
            return
        if not args.no_header:
            print("node")
            print("----")
        for n in nodes:
            print(n)
        return
    if args.list_vmids:
        vmids = sorted({str(vm.get("vmid")) for vm in vm_info if vm.get("vmid")})
        if args.output == "json":
            print(json.dumps(vmids, indent=2))
            return
        if args.output == "csv":
            for vid in vmids:
                print(vid)
            return
        if not args.no_header:
            print("vmid")
            print("----")
        for vid in vmids:
            print(vid)
        return
    if args.cluster_info:
        corosync_data = parse_corosync_conf()
        corosync_nodes = {}
        corosync_cluster_name = None
        if corosync_data:
            corosync_nodes = corosync_data.get("nodes", {}) or {}
            corosync_cluster_name = corosync_data.get("cluster_name")
        cluster_name_ci = corosync_cluster_name or cluster_name or "standalone"
        try:
            nodes_list = run_pvesh(["get", "/nodes", "--output-format", "json"])
        except subprocess.CalledProcessError as e:
            print("Error running pvesh /nodes:", e.stderr, file=sys.stderr)
            sys.exit(1)
        if not nodes_list:
            nodes_list = []
        rows_ci = []
        for ninfo in nodes_list:
            node_name = ninfo.get("node")
            if not node_name:
                continue
            if node_filter and node_name not in node_filter:
                continue
            cluster_ip = corosync_nodes.get(node_name, "")
            ext_ip, ext_cidr, ext_gw = get_node_external_info(node_name)
            if not corosync_nodes and ext_ip and not cluster_ip:
                cluster_ip = ext_ip
            row = {
                "cluster": cluster_name_ci,
                "node": node_name,
                "cluster_ip": cluster_ip or "",
                "external_ip": ext_ip or "",
                "external_cidr": ext_cidr or "",
                "external_gw": ext_gw or "",
            }
            rows_ci.append(row)
        rows_ci.sort(key=lambda r: r["node"])
        headers_ci = [
            "cluster",
            "node",
            "cluster_ip",
            "external_ip",
            "external_cidr",
            "external_gw",
        ]
        if args.output == "json":
            print(json.dumps(rows_ci, indent=2))
            return
        if args.output == "csv":
            if not args.no_header:
                print(";".join(headers_ci))
            for r in rows_ci:
                print(";".join(str(r[h]) for h in headers_ci))
            return
        if rows_ci or not args.no_header:
            print_table(headers_ci, rows_ci, human=False)
        return
    if args.list_storages:
        try:
            nodes_list = run_pvesh(["get", "/nodes", "--output-format", "json"])
        except subprocess.CalledProcessError as e:
            print("Error running pvesh /nodes:", e.stderr, file=sys.stderr)
            sys.exit(1)
        if not nodes_list:
            nodes_list = []
        storage_rows = []
        for ninfo in nodes_list:
            node_name = ninfo.get("node")
            if not node_name:
                continue
            if node_filter and node_name not in node_filter:
                continue
            try:
                stor_list = run_pvesh(
                    [
                        "get",
                        f"/nodes/{node_name}/storage",
                        "--output-format",
                        "json",
                    ]
                )
            except subprocess.CalledProcessError as e:
                sys.stderr.write(
                    f"Warning: cannot get storage list for node {node_name}: {e.stderr}\n"
                )
                continue
            if not stor_list:
                continue
            for s in stor_list:
                storage_id = s.get("storage")
                stype = s.get("type", "")
                if not storage_id:
                    continue
                try:
                    st_status = run_pvesh(
                        [
                            "get",
                            f"/nodes/{node_name}/storage/{storage_id}/status",
                            "--output-format",
                            "json",
                        ]
                    )
                except subprocess.CalledProcessError as e:
                    sys.stderr.write(
                        f"Warning: cannot get storage status for {node_name}/{storage_id}: {e.stderr}\n"
                    )
                    continue
                if not st_status:
                    continue
                total_b = st_status.get("total", 0) or 0
                used_b = st_status.get("used", 0) or 0
                avail_b = st_status.get("avail", 0) or 0
                total_mb = int(total_b // (1024 * 1024)) if total_b else 0
                used_mb = int(used_b // (1024 * 1024)) if used_b else 0
                avail_mb = int(avail_b // (1024 * 1024)) if avail_b else 0
                if total_mb > 0:
                    used_pct = (used_mb * 100.0) / total_mb
                    avail_pct = 100.0 - used_pct
                else:
                    used_pct = 0.0
                    avail_pct = 0.0
                storage_rows.append(
                    {
                        "cluster": cluster_name,
                        "node": node_name,
                        "storage": storage_id,
                        "type": stype,
                        "total_MB": total_mb,
                        "used_MB": used_mb,
                        "available_MB": avail_mb,
                        "used_%": f"{used_pct:.2f}",
                        "available_%": f"{avail_pct:.2f}",
                    }
                )
        storage_rows.sort(key=lambda r: (r["node"], r["storage"]))
        headers_st = [
            "cluster",
            "node",
            "storage",
            "type",
            "total_MB",
            "used_MB",
            "available_MB",
            "used_%",
            "available_%",
        ]
        if args.output == "json":
            print(json.dumps(storage_rows, indent=2))
            return
        if args.output == "csv":
            if not args.no_header:
                print(";".join(headers_st))
            for r in storage_rows:
                print(";".join(str(r[h]) for h in headers_st))
            return
        if storage_rows or not args.no_header:
            print_table(headers_st, storage_rows, human=args.human)
        return
    vm_entries = []
    for vm in vm_info:
        vmid = vm.get("vmid")
        node = vm.get("node")
        vmname = vm.get("name")
        vtype = vm.get("type")
        if vmid is None or node is None:
            continue
        vmid_str = str(vmid)
        if vmid_filter and vmid_str not in vmid_filter:
            continue
        if node_filter and node not in node_filter:
            continue
        vm_entries.append(
            {
                "vmid": vmid_str,
                "node": node,
                "vmname": vmname,
                "type": vtype,
            }
        )
    if not vm_entries:
        if (
            args.output == "csv"
            and not (args.total_per_vm or args.total_per_node or args.vm_per_storage)
            and not args.no_header
        ):
            print("cluster;node;vmid;vmname;storage;vmdisk;size;size_MB")
        elif (
            args.output == "table"
            and not (args.total_per_vm or args.total_per_node or args.vm_per_storage)
        ):
            pass
        sys.exit(0)
    if args.workers and args.workers > 0:
        workers = args.workers
    else:
        workers = min(8, len(vm_entries))
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_vm = {
            executor.submit(fetch_vm_disks, cluster_name, vm_entry): vm_entry
            for vm_entry in vm_entries
        }
        for future in as_completed(future_to_vm):
            vm_entry = future_to_vm[future]
            try:
                disk_rows = future.result()
                rows.extend(disk_rows)
            except Exception as e:
                sys.stderr.write(
                    f"Error processing {vm_entry['type']} {vm_entry['vmid']} on {vm_entry['node']}: {e}\n"
                )
    if args.vm_per_storage:
        vm_stor_totals = defaultdict(int)
        vm_meta = {}
        for r in rows:
            key = (r["node"], r["vmid"], r["vmname"], r["storage"])
            vm_stor_totals[key] += r["size_mb"]
            vm_meta[key] = (r["cluster"], r["vmname"])
        result = []
        for key, mb in vm_stor_totals.items():
            node, vmid, vmname, storage = key
            cluster_val, vmname_val = vm_meta[key]
            result.append(
                {
                    "cluster": cluster_val,
                    "node": node,
                    "vmid": vmid,
                    "vmname": vmname_val,
                    "storage": storage,
                    "size_MB": mb,
                }
            )
        result.sort(key=lambda r: (r["node"], int(r["vmid"]), r["storage"]))
        headers = ["cluster", "node", "vmid", "vmname", "storage", "size_MB"]
        if args.output == "json":
            print(json.dumps(result, indent=2))
            return
        if args.output == "csv":
            if not args.no_header:
                print(";".join(headers))
            for r in result:
                print(";".join(str(r[h]) for h in headers))
            return
        if result or not args.no_header:
            print_table(headers, result, human=args.human)
        return
    if args.total_per_vm:
        totals = {}
        for r in rows:
            vmid = r["vmid"]
            if vmid not in totals:
                totals[vmid] = {
                    "cluster": r["cluster"],
                    "node": r["node"],
                    "vmname": r["vmname"],
                    "total_size_MB": 0,
                }
            totals[vmid]["total_size_MB"] += r["size_mb"]
        result = [
            {
                "cluster": v["cluster"],
                "node": v["node"],
                "vmid": vmid,
                "vmname": v["vmname"],
                "total_size_MB": v["total_size_MB"],
            }
            for vmid, v in totals.items()
        ]
        result.sort(key=lambda r: (r["node"], int(r["vmid"])))
        headers = ["cluster", "node", "vmid", "vmname", "total_size_MB"]
        if args.output == "json":
            print(json.dumps(result, indent=2))
            return
        if args.output == "csv":
            if not args.no_header:
                print(";".join(headers))
            for r in result:
                print(";".join(str(r[h]) for h in headers))
            return
        if result or not args.no_header:
            print_table(headers, result, human=args.human)
        return
    if args.total_per_node:
        totals = defaultdict(int)
        for r in rows:
            totals[r["node"]] += r["size_mb"]
        result = [
            {
                "cluster": cluster_name,
                "node": node,
                "total_size_MB": mb,
            }
            for node, mb in totals.items()
        ]
        result.sort(key=lambda r: r["node"])
        headers = ["cluster", "node", "total_size_MB"]
        if args.output == "json":
            print(json.dumps(result, indent=2))
            return
        if args.output == "csv":
            if not args.no_header:
                print(";".join(headers))
            for r in result:
                print(";".join(str(r[h]) for h in headers))
            return
        if result or not args.no_header:
            print_table(headers, result, human=args.human)
        return
    rows.sort(
        key=lambda r: (r["node"], int(r["vmid"]), r["storage"], r["vmdisk"])
    )
    if args.output == "json":
        print(json.dumps(rows, indent=2))
        return
    headers = [
        "cluster",
        "node",
        "vmid",
        "vmname",
        "storage",
        "vmdisk",
        "size",
        "size_mb",
    ]
    if args.output == "csv":
        if not args.no_header:
            print(";".join(headers))
        for r in rows:
            print(";".join(str(r[h]) for h in headers))
        return
    if rows or not args.no_header:
        print_table(headers, rows, human=args.human)


if __name__ == "__main__":
    main()
