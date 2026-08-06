# FAQ

## Installation & Deployment

1. What deployment methods are supported?

Docker Compose is the supported deployment path for users. Running from source is intended for contributors and is not the usual deployment route; install Docker first.

2. What platforms are supported?

Windows, macOS, and Linux are supported. Both x86 and ARM architectures are supported.

## External Libraries

1. External library setup fails — "directory does not exist"

[See Directory Settings](./settings/directories.md)

## AI-Related

1. How to use the API to analyze photos, or how to view results after analysis

[See AI Settings](./settings/aisetting.md)

## Scanning, tasks, and photos

1. Is a long first scan normal?

Yes. Scanning and AI analysis time depend on the number of photos, disk speed, and model configuration. Check the task page and service logs, and validate the workflow with a small folder before importing a full library.

2. Why cannot TrailSnap find my photos or access the folder?

Confirm that the host photo directory exists, is mounted into Docker, and is readable by the service. Organize, rename, and cleanup features also need write permission. See the [pre-deployment checklist](/en/docs/guide/preflight).

## Mobile and networking

1. Why cannot my phone reach the server?

Put the phone and server on the same LAN, use the server's LAN IP instead of `localhost`, then check Docker port mappings, the firewall, and Wi-Fi AP isolation. See the [Mobile App Guide](/en/docs/guide/mobile-app) for the Android address format.

## Backups and upgrades

1. What should I do before an upgrade?

Back up both the photo directory and PostgreSQL database, then read the [changelog](/en/docs/guide/changelog). Backing up only one may leave data inconsistent.

2. How can I use external AI or Agent tokens safely?

Grant only the required scope, never publish tokens, and use HTTPS for public access. See [Data, privacy, and backups](/en/docs/guide/data-safety).
