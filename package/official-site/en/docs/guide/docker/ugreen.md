---
title: Ugreen NAS Deployment
---

# Ugreen NAS Deployment

## Deploy Container using Docker Compose

On the UGOS Pro system, it is recommended to use the project Docker Compose to quickly deploy containers, suitable for scenarios where multiple containers need to be managed simultaneously. This method simplifies container deployment and management. The following are the detailed steps to deploy TrailSnap using Docker Compose.

If you haven't deployed before, it is recommended to read the generic chapter first: [/en/docs/guide/docker/](/en/docs/guide/docker/)

### 1. Enter Docker Project Interface

In the UGOS Pro system, open the Docker application, click [Project] > [Create], and start the project creation wizard.
Fill in the project name as `trailsnap`, and leave others as default.

## 2. Configure Docker Compose File

Fill in the Docker Compose template from [/en/docs/guide/docker/](/en/docs/guide/docker/).

1. Modify the photo directory mount for the `server` service:

```yaml
volumes:
  - ./data:/app/data
  - /real/path/to/your/photos:/app/Photos/
```

If you want to maximize security, you can mount the photo directory as read-only:

```yaml
- /real/path/to/your/photos:/app/Photos/:ro
```

## 3. Set Ports and Network

TrailSnap exposes one access port by default: `8082`. The browser, App, and CLI use this address; Server, AI, and database ports stay inside Docker.

If it conflicts with another NAS service, modify only `frontend.ports` (for example, use 18082).

## 4. Startup and Verification

Access in browser after startup:

- `http://<NAS_IP>:8082`

Open Settings -> External Libraries, fill in the photo path inside the container: `/app/Photos/`, adding an external library will automatically scan and run tasks in the background (task details can be viewed in Settings -> Task Management).

API documentation is available at `http://<NAS_IP>:8082/api/docs`.

## 5. Permission and Scan Troubleshooting

If TrailSnap cannot scan photos, it is usually a permission or path problem:

- First enter the terminal/console of the `server` container and confirm that photo files can be seen in the `/app/Photos/` directory.
- Confirm that the NAS side shared folder permissions allow Docker/container service reading.
- If the photo directory is on external storage or a specific storage pool, confirm that the storage pool is visible to the container.
