---
outline: [2, 3]
---

# Data, privacy, and backups

TrailSnap is self-hosted: your photos, database, and account data are stored on the server or NAS you operate. Installing TrailSnap does not automatically send photos to the project maintainers, but the person operating the server remains responsible for access control, backups, and public-network security.

## Where data is stored

| Data | Default location | What to keep in mind |
| --- | --- | --- |
| Original photos and thumbnails | The photo directory mounted into the service | Do not move or delete files directly while tasks are running |
| Albums, accounts, tasks, and indexes | PostgreSQL volume | Back up before upgrades or migrations |
| AI analysis results | Database and related storage | Clean related tasks and results as needed after deletion |
| Agent tokens | TrailSnap database | Grant the minimum scope and revoke leaked tokens immediately |

## Data boundaries when using AI

- With local models or a locally hosted LLM, inference data stays on your devices and server.
- When you configure OpenAI, a remote Ollama instance, or another third-party model provider, the data sent depends on the enabled feature and provider configuration. Read that provider's privacy policy first and do not send sensitive photos to untrusted services.
- Never publish API keys, Agent tokens, or screenshots containing complete tokens in issues, chats, or logs.

## Deployment security checklist

1. Use strong TrailSnap account passwords, even on a home LAN.
2. For public access, use a domain, HTTPS, and a reverse proxy. Do not directly expose PostgreSQL, management ports, or the Docker socket.
3. Expose only necessary ports to trusted networks. Mobile App access over the public internet must use HTTPS.
4. Update TrailSnap and Docker images regularly; read the [changelog](/en/docs/guide/changelog) before upgrading.
5. Give each shared-server user a separate account instead of sharing admin credentials or tokens.

## Backup and recovery

Back up both the **photo directory** and the **PostgreSQL database**. Restoring only one can leave photo files and album records inconsistent.

- Back up photos incrementally or continuously to a separate disk / NAS.
- Back up the database daily and once more before upgrades, migrations, batch organization, or cleanup.
- Periodically test a restore; a backup is useful only when it can be restored.

During recovery, stop relevant services, restore photos and database from the same point in time, then verify photo counts, albums, accounts, and task status. Check your own `docker-compose.yml` and `.env` for the actual volumes and paths before running any backup or restore command.

## Deleting data

Deleting a photo, album, or account in the app does not automatically erase every backup. For full deletion, also check the photo directory, database backups, synced storage, and any relevant records held by third-party AI services.
