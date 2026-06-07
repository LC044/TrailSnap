# Changelog

## 2026-06-07 (0.5.0)

### New

- Added **Sidebar navigation**: redesigned frontend layout with collapsible sidebar.
- Sidebar shows hover tooltips when collapsed.
- Added **Sidebar global search**: quickly find photos, albums, people, etc.
- Added **Theme customization**: choose from 5 brand colors (Sky, Emerald, Violet, Rose, Amber) that apply globally with one click.
- Unified theme handling with reusable components.

### Improvements

- Optimized location map page; refactored backend photo query logic.
- Improved multi-module query performance.
- Fixed album page theme color not responding and dark mode contrast issues.
- Fixed missing primary theme utility class mappings (hover/shadow not following theme).
- Unified icons and refined frontend conventions.
- Improved page UI layout and fixed import issues.

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
