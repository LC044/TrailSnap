---
outline: [2, 3]
---

# Pre-deployment checklist

Use this page before running the installer. It helps avoid the common case where containers start successfully but photos cannot be scanned or a phone cannot reach the server.

## What you need

| Item | Minimum | Recommended |
| --- | --- | --- |
| System | Windows, macOS, Linux, or a Docker-capable NAS | A supported 64-bit x86 or ARM system with current Docker |
| Docker | Docker Engine / Desktop and Docker Compose | Confirm with `docker compose version` first |
| Storage | Space for original photos, thumbnails, and the database | Reserve headroom and a separate backup destination |
| Network | A browser can reach the server | Use the same LAN for phones, or configure HTTPS public access |
| AI | CPU is enough for the basic flow | Larger libraries or local models benefit from more memory and a GPU; a GPU is not required to install |

## Check your photo directory

- Use an existing absolute host path, not a temporary drive, disconnected network mapping, or a container path.
- Ensure Docker can read the directory. Upload, organize, rename, and cleanup features also require appropriate write access.
- Back up photos before the first import. Test file-changing tools on a small directory first.
- Initial scanning time depends on photo count, file sizes, disk speed, and enabled AI. It runs in the background and does not mean the web app is unavailable.

## Network and ports

- The installer normally exposes separate Web frontend and backend API ports; use the generated `.env` and installer output as the source of truth.
- A phone browser uses the Web frontend port. Android App setup uses the backend API address and must not use `localhost`.
- If LAN access fails, inspect Docker port mapping, the firewall, and Wi-Fi AP / guest-network isolation.

## Choose your starting path

1. **Trying TrailSnap**: deploy in CPU mode with a small test folder.
2. **Importing a family library**: back up the photos and database, then run the first scan during an idle period.
3. **Using mobile or public access**: plan a domain and HTTPS first; never expose database ports publicly.
4. **Using third-party AI or an Agent**: read [Data, privacy, and backups](/en/docs/guide/data-safety) and grant tokens the minimum scope.

When ready, continue to the [installation guide](/en/docs/guide/install).
