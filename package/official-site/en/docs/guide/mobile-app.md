---
title: Mobile App Guide
description: Install the TrailSnap Android app and connect it to your own TrailSnap server
---

# Mobile App Guide

The TrailSnap app is a Capacitor-based native container for the web application. It does not connect
to a public TrailSnap cloud service. Instead, it connects to the TrailSnap backend that you deploy and
control. Complete the [server installation](/en/docs/guide/install) before installing the app.

::: warning Preview version
The mobile app currently focuses on essential features such as sign-in, album browsing, search, and
settings. Some native integrations are still under development, so keeping browser access available is
recommended.
:::

## Install on Android

1. Open the project's [GitHub Releases](https://github.com/LC044/TrailSnap/releases).
2. Find a release named `TrailSnap App` or with a tag beginning with `app-v`.
3. Download the APK from **Assets**. Early test packages may include `debug` in the file name.
4. Open the APK and allow your browser or file manager to install unknown apps when Android asks.
5. Open TrailSnap after installation.

Only download packages from the official TrailSnap GitHub repository. If a SHA-256 checksum is published
on the Release page, compare it before installation. If Play Protect displays a warning, verify the source
and any published checksum before continuing.

## Connect to Your Server

On first launch, enter the **main backend URL** without `/api`:

```text
http://192.168.1.10:8800
```

- Replace `192.168.1.10` with the LAN IP address of the computer or NAS running TrailSnap.
- `8800` is the default backend API port used by the installation scripts.
- Do not use `localhost` or `127.0.0.1`; on a phone, those addresses refer to the phone itself.
- Do not enter the web frontend port `8082`.
- Do not append `/api` to the URL.

Tap **Test and Save**. After a successful connection, the app stores the address and opens the sign-in
page. Accounts, photos, and albums remain on your TrailSnap server.

### Connection Checklist

Connect the phone and server to the same LAN, then open this URL in the phone's browser:

```text
http://192.168.1.10:8800/health-check
```

If it does not open, check that:

- the TrailSnap `server` container is running;
- Docker maps the backend port as `8800:8000`;
- the server firewall allows inbound TCP traffic on port `8800`;
- Wi-Fi client/AP isolation is disabled;
- the IP address and port are correct.

HTTP can be used on a trusted LAN. For access over the public internet, configure a domain and a valid
HTTPS certificate to protect credentials, tokens, and photo requests in transit.

## Change Servers

Open:

```text
Settings → About → Change Server
```

Enter the new address and tap **Test and Save**. Switching servers clears the current sign-in state, so
you must sign in with an account on the new server. It does not delete photos or settings stored on either
server.

## Android Back Navigation

The Android hardware button or back gesture behaves in this order:

1. close the current dialog;
2. return to the previous page when available;
3. move TrailSnap to the background at the root page instead of terminating the app.

## Update the App

Download the newer APK from GitHub Releases and install it over the existing version. An in-place update
requires the same application ID and signing key, plus a newer version number.

A normal update keeps the saved server address and sign-in state. If Android reports a signature mismatch,
do not uninstall immediately; first verify that the APK came from the official Release. Uninstalling clears
the server address and token stored on the phone, but it does not delete server-side photos or databases.

## iPhone and iPad

The native iOS project is available, but a public IPA still requires Apple developer signing. For now, use
TrailSnap as a PWA:

1. Open the TrailSnap web URL in Safari, for example `http://192.168.1.10:8082`.
2. Tap Safari's **Share** button.
3. Select **Add to Home Screen**.
4. Open TrailSnap from the Home Screen.

The PWA uses the web frontend port `8082`; this differs from the backend port `8800` entered in the Android app.

## Privacy and Security

- The app connects to the server selected by the user; using the app does not automatically give project maintainers access to photos or account data.
- The server operator remains responsible for protecting the database, photo directories, backups, and credentials.
- Prefer HTTPS and strong passwords for public internet access.
- Do not expose database or administrative ports directly to the internet.
- Keep the app, server, and web frontend on compatible versions to avoid API incompatibilities.
