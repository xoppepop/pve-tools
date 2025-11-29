# pve-storage-info

A lightweight, fast, parallelized storage-inspection tool for **Proxmox VE**.  
It collects detailed information about VM and container disks across a cluster, aggregates storage usage, and provides multiple output formats (table, CSV, JSON).

---

## Features

- Lists all VM/LXC disks:
  - **QEMU:** SCSI / VirtIO / IDE / SATA
  - **LXC:** rootfs, mpX mounts (NOT TESTED)
- Per-node storage usage
- Per-VM aggregated usage
- Per-storage aggregated usage
- Cluster/ring0/external IP information
- Parallel pvesh calls for high speed (NOT TESTED)
- Output formats: **table**, **csv**, **json**

---

# Installation

## Quick install (curl | sh)

```bash
curl -fsSL https://raw.githubusercontent.com/xoppepop/pve-tools/main/install.sh | sh
```

This installs:

- `/opt/pve-tools/pve-storage-info.py`
- symlink: `/usr/local/bin/pve-storage-info`

Run the tool:

```bash
pve-storage-info
```

---

# Manual installation

```bash
mkdir -p /opt/pve-tools
cd /opt/pve-tools

curl -O https://raw.githubusercontent.com/xoppepop/pve-tools/main/pve-storage-info.py
chmod +x pve-storage-info.py

ln -s /opt/pve-tools/pve-storage-info.py /usr/local/bin/pve-storage-info
```

---

# Usage

```bash
pve-storage-info [OPTIONS]
```

---

# Options

## Filtering

### Filter by VMID(s)
```bash
--vmid 100,101,121
```

### Filter by node(s)
```bash
--node pve01,pve02
```

---

## Output control

### Output formats
```bash
--output table    # default
--output csv
--output json
```

### Disable header in CSV
```bash
--no-header
```

### Human-readable sizes (table mode only)
```bash
--human
```

---

## Parallelism

### Number of worker threads
```bash
--workers 8
```

Default: up to 8 depending on VM count.

---

# Listing modes

### List all cluster nodes
```bash
--list-nodes
```

### List all VMIDs
```bash
--list-vmids
```

### List storages per node
```bash
--list-storages
```

Shows:

- total MB  
- used MB  
- available MB  
- used %  
- available %

---

# Aggregation modes

### Per-VM total disk usage
```bash
--total-per-vm
```

### Per-node total disk usage
```bash
--total-per-node
```

### Per-storage usage per VM
```bash
--vm-per-storage
```

---

# Cluster information

### Show cluster/ring0/external IP information
```bash
--cluster-info
```

Outputs:

- cluster name  
- node name  
- ring0 (corosync) IP  
- external IP  
- external CIDR  
- external gateway  

---

# Examples

### List all disks in cluster
```bash
pve-storage-info
```

### Show disks for VM 120
```bash
pve-storage-info --vmid 120
```

### CSV output without header
```bash
pve-storage-info --output csv --no-header
```

### Human-readable table
```bash
pve-storage-info --human
```

### Show per-node storage usage
```bash
pve-storage-info --list-storages
```

### Show per-VM aggregated usage
```bash
pve-storage-info --total-per-vm
```

---

# License

BSD 2-Clause License  
© 2025 xoppepop
