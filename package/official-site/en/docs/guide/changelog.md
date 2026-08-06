# Changelog

## 2026-08-02 (0.9.1)

### New

- Added Capacitor-based Android/iOS App projects. On first launch, the App lets users enter and save their self-hosted TrailSnap Server address.
- Added automated Android APK builds. Pushing a `v*.*.*` tag uploads the APK and CLI artifacts to the same GitHub Release.
- Added PWA support to the Web frontend, including installability and improved offline / refresh behavior.
- AI Moments copy generation can now show its reasoning progress in real time.

### Improvements

- Improved Android back-button and gesture behavior: close overlays first, navigate back next, then move to the background from the home screen.
- Unified App and CLI publishing rules: manual builds keep Actions artifacts, while version tags create or update Releases.
- Added mobile App installation, server configuration, update, and privacy guidance to the official site.

### Bug Fixes

- Fixed executable permissions for the Android Gradle Wrapper on Linux GitHub runners.
- Fixed PWA refresh behavior and branch image-tag handling.

## 2026-08-02 (0.9.0)

### New

- Added **Moments Diary**: generate, edit, and clear AI social copy by day, with main locations and photo highlights.
- Added **location album collage view** with nationwide / province browsing, automatic or manual photo selection, tile replacement, and similar-photo removal.
- Added map double-click drill-down and collage selection strategies including memory value, quality, latest, and random.
- Added mobile bottom-tab navigation, map/collage gestures, and an Agent drawer.

### Improvements

- Reduced Server and AI image size and startup overhead; added graceful stopping and health monitoring to the AI service.
- Improved social-image aspect ratios, mobile layout, and collage rendering performance.

### Bug Fixes

- Fixed timezone aggregation, streaming generation, and single-image aspect ratio issues for Moments copy.
- Fixed mobile collage blank screens, reverse-geocoding parsing, and several external-library and task-navigation issues.

## 2026-07-28 (0.8.1)

### New

- Added an **external photo library setup wizard** for directory selection, path mapping, and scan configuration.
- Added a global notification center for background tasks and system messages.
- Added scheduled version-update checks.

### Improvements

- Improved AI assistant context trimming and photo retrieval for long conversations and complex libraries.
- Expanded automated coverage for the frontend, server, and AI service.

### Bug Fixes

- Fixed reinstall, health-check, metadata dispatch, and AI-timeout issues affecting some deployments.

## 2026-07-11 (0.7.0)

### New

- Added **"Letting Go" photo filter**: swipe left/right to quickly decide each photo's fate — an easy way to declutter a bloated library.
- Added **Storage Center**: a unified view of storage usage across sources; the home storage card jumps straight to the corresponding photo filter.
- Photo editing now **preserves original EXIF metadata** (capture time, location, etc.), so timelines and map pins stay accurate.
- The AI assistant floating button now supports **free dragging and auto half-hiding at screen edges**.
- Clicking the search box now **pre-warms the AI service** to avoid first-search cold-start delay.
- First-time users are redirected straight to the registration page.
- The install script now **auto-configures a China Docker mirror** and enables it by region.

### Improvements

- The recycle bin now supports a selection mode for batch restore/delete.
- Improved mobile experience for the Settings and Toolbox pages.

### Bug Fixes

- Fixed the photo location-edit popup failing to reopen after being closed.
- Fixed the worker watchdog restarting in a loop when only paused tasks remained.

## 2026-06-07 (0.4.1)

### New

- Added **Photo editing**: crop, rotate, doodle, text, and shape tools.
- Added **Sidebar navigation**: redesigned frontend layout with collapsible sidebar.
- Sidebar shows hover tooltips when collapsed.
- Added **Sidebar global search**: quickly find photos, albums, people, etc.
- Added **Theme customization**: choose from 5 brand colors (Sky, Emerald, Violet, Rose, Amber) that apply globally with one click.
- Added **Custom sidebar navigation items**: customize the sidebar navigation menu.
- Unified theme handling with reusable components.

### Improvements

- Optimized location map page and view component; refactored backend photo query logic.
- Improved multi-module query performance.
- Unified icons and refined frontend conventions.
- Improved page UI layout and fixed import issues.

### Bug Fixes

- Fixed album page theme color not responding and dark mode contrast issues.
- Fixed missing primary theme utility class mappings (hover/shadow not following theme).

## 2026-05-28 (0.4.0)

### New

- Photo organize toolbox now supports "Time directory structure" option — flat or recursive nested structure (e.g. `2026/01/01`).
- Photo organize supports automatic grouping by person.
- Added **Built-in AI connection**: works out of the box, using MiniCPM-V-4_6-Q4_K_M multimodal model by default.
- Added **Local LLM hosting**: host custom models via llama.cpp.

### Improvements

- Migrated all AI services to ONNX Runtime, removing redundant dependencies.
- Refactored AI service LLM deployment logic — replaced pyllama-cpp-python with natively compiled llama-server binary.
- Implemented priority-based task filtering when queue is full.
- Improved image processing with WebP format auto-conversion.
- Improved LLM settings page with built-in connection badge.
- Improved failed task cleanup mechanism.
- Fixed organize task progress calculation error.

## 2026-05-14 (0.3.9)

### New

- Added "Skiing" category to smart classification.
- Smart classification now supports setting cover photos.
- Added ability to delete recognized people.

### Improvements

- Thumbnails now use WebP format to reduce file size.
- Fixed task priority anomalies.
- Improved smart classification accuracy, reducing misclassification.
- Improved some UI details.

## 2026-04-28 (0.3.8)

### New

- Added **Recycle Bin**: restore deleted photos.
- Added **TrailSnap CLI**: interact with TrailSnap via command line.
- Added **Skills integration**: connect to OpenClaw, Claude Code, etc.

### Improvements

- Improved some UI details.
- Improved AI chat experience.

## 2026-04-22 (0.3.6)

### Improvements

- Fixed tasks occasionally getting stuck.
- Optimized task process management to reduce memory usage.
- Speeded up LLM task processing to reduce waiting time.
- Improved AI chat thinking/tool visualization so users can see intermediate steps.
- Improved smart classification accuracy.

## 2026-04-18 (0.3.3) [vibe coding prompt](/docs/dev/prompt/0.3.3)

### New

- Added manual photo classification so users can correct misclassified photos.
- Added multiple LLM connections so users can choose which model to use.

### Improvements

- Improved photo classification and ticket recognition accuracy.
- Improved task processing efficiency to reduce waiting time.
- Fixed photo delete failing in some scenarios.
- Supported legacy Apple Live Photo formats (`.jpg` + `.mov`).
- Improved some UI details.

## 2026-03-29 (0.3.2) [vibe coding prompt](/docs/dev/prompt/0.3.2)

### New

- Added **AI Assistant**: chat with LLMs to search and understand your album content.
- Added **Footprint Timeline** in location albums: browse photos by time across locations.
- Added **Trajectory View**: connect photo locations across a time range to show travel routes.
- Added **Token Management**: create tokens for third-party apps to access album data without logging in.

### Improvements

- Location album and ticket stats pages support custom time ranges.
- Fixed metadata parsing failures for Apple HEIC photos.
- Improved search: fixed scenic spot search issues and improved suggestion loading speed.
- Improved some UI details.

## 2026-03-21 (0.3.1) [vibe coding prompt](/docs/dev/prompt/0.3.1)

### New

- Added **Similar Photos Cleanup**.
- Added **Photo Calendar** on the home page.
- Video playback supports speed control.

### Improvements

- Fixed leftover Live Photo/thumbnail files after deletion.
- Fixed black screen when switching videos.
- Improved people album loading speed.
- Fixed permission issues in ticket recognition.
- Improved some UI details.

## 2026-03-12 (0.3.0) [vibe coding prompt](/docs/dev/prompt/0.3.0)

### New

- Added multi-user support with data isolation.
- Added LLM photo analysis: generate descriptions and scores.
- Added **On This Day**: browse photos from past years, sorted by score.
- Added **Album Cleanup**: clean analyzed photos based on scores.

### Improvements

- Support hiding a people album.
- Support adding photos to a people album.
- Improved face recognition accuracy.
- Improved some UI details.

## 2026-02-25 (0.2.3) [vibe coding prompt](/docs/dev/prompt/0.2.3)

### New

- Added image file filtering.
- Location albums support filtering by year.

### Improvements

- Fixed photo ordering issues in people albums.
- Improved page layout and UI.

## 2026-02-05 (0.2.2) [vibe coding prompt](/docs/dev/prompt/0.2.2)

### New

- Support exporting paper-style train tickets (blue/red).

### Improvements

- Added Tianditu tile caching to reduce network requests.
- Improved location map rendering.
- Fixed resource release issues in metadata rebuild tasks.
- Improved UI display in some pages.

## 2026-02-01 (0.2.0) [vibe coding prompt](/docs/dev/prompt/0.2.0)

### New

- Supported iPhone Live Photos.
- Supported downloading offline maps for multiple countries, or uploading custom map data (requires rerunning **Metadata Extraction** task).
- Added 358 5A scenic spots in China to the map album (requires rerunning **Metadata Extraction** task).
- Supported editing custom scenic spot locations.
- Supported searching by text, location, people, album, folder, filename, etc.
- Supported recognizing flight tickets (order screenshots), requires rerunning **Ticket Recognition** task.
- Supported ticket import/export (CSV/JSON).

### Improvements

- Fixed duplicate photo display.
- Fixed missing default covers after rerunning face recognition tasks.
- Improved ticket recognition accuracy and speed.
- Fixed upload failure for images larger than 1MB.
- Improved some UI details.

## 2026-01-17 (0.1.0)

| Feature | Status | Description |
| --- | --- | --- |
| Upload & view photos/videos | ✓ | Upload local photos and videos, view and play them. |
| Add external folders | ✓ | Add external folders as data sources; TrailSnap will scan and index photos/videos automatically. |
| Live Photo | ✓ | Support vivo/oppo/xiaomi and more. |
| Timeline | ✓ | Smooth timeline scrolling experience. |
| View photos on map | ✓ | View all uploaded photos on a map; filter by province/city/district; list & map views supported. |
| Lit-up cities | ✓ | See cities appearing in photos; click a city to browse its photos. |
| Visited scenic spots | In Dev | Count visited 5A scenic spots; support custom scenic spot areas; auto filter photos within the area. |
| Face recognition | ✓ | Recognize people in photos and add people tags. |
| Smart scene classification | ✓ | Auto classify scenes, e.g. night view, pets, food, selfie. |
| Smart search | ✓ | Search by people, content, time, etc. |
| Tags | ✓ | Add/remove tags manually, or auto-tag based on AI results. |
| Smart albums | ✓ | Auto generate albums from content, e.g. “Selfies by the sea with my girlfriend”. |
| Ticket recognition | In Dev | Recognize train tickets and itineraries, auto extract travel info. |
| Annual report | In Dev | Auto generate yearly travel report: photo wall, cities, scenic spots, travel timeline, mileage, etc. |
| Travel log | Planned | Generate travel logs from manual input or AI-recognized itinerary. |
