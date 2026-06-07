# Feature Design Document

This document collects design drafts for upcoming TrailSnap features, serving as a reference for community discussion and contributions.

---

## 1. Image Editing

### 1.1 Background & Goals

Users can currently only view photos, lacking basic editing capabilities. Image editing is a high-frequency need for album applications and lays the groundwork for features like "Social Media 9-Grid Generator" down the line.

### 1.2 Feature Scope

**Basic Editing**
- Crop (free crop, aspect ratio crop such as 1:1, 16:9)
- Rotate (90°, horizontal flip, vertical flip)
- Zoom & drag

**Tags & Annotations**
- Add text labels (with font, color, size options)
- Add simple shapes such as arrows and selection boxes
- Add time and location watermarks

**Filters & Adjustments**
- Basic adjustments: brightness, contrast, saturation
- Preset filters: vintage, black & white, soft, etc.

### 1.3 Technical Approach

- Use Canvas API or WebGL on the frontend for lossless editing
- Editing results support export to original-quality JPEG/PNG
- Edit history (Undo/Redo)

### 1.4 Priority

**Medium** — to be developed as part of the Toolbox module

---

## 2. Photo Auto-Organize

### 2.1 Background & Goals

Photos accumulate haphazardly over time, and manual organization is tedious. AI can automatically categorize photos by time, location, content, and other dimensions, reducing the user's effort.

### 2.2 Organization Rules

| Rule | Description | Example |
| --- | --- | --- |
| By year & month | Create `2024/2024-03` or `2024-03` folder | 2024/2024-03 or 2024-03 |
| By date | Create `2024/2024-03-15` or `2024-03-15` folder | 2024/2024-03-15 or 2024-03-15 |
| By person | Create `Person-Zhang San/` folder | Face photos of Zhang San |
| By scene | Create `Food/`, `Pets/` folders | Classified photos |

### 2.3 Technical Approach

- Use existing metadata (EXIF, geolocation, face tags, scene classification)
- Copy or move photos (user's choice)
- Support previewing results before executing
- Log organization operations, support undo
- **New: support both flat and recursive nested time directory formats**

### 2.4 Status

**Implemented** — Toolbox → Photo Auto-Organize

### 2.5 Priority

~~**Medium**~~ → Launched

---

## 3. Auto Travel Journal

### 3.1 Background & Goals

After a trip, users often need to manually sort photos and write travelogues — a tedious process. AI can automatically generate structured travel records from photos, tickets, locations, and other data.

### 3.2 Input Data

- Photos from the trip (with metadata)
- Recognized train tickets, flight tickets, admission tickets
- Geographic location tracks
- Possible AI descriptions and ratings

### 3.3 Output Content

**Structured Journal**
- Title: trip name (e.g., "March 2024 Xiamen Trip")
- Time: departure date, return date, total days
- Itinerary: daily timeline
- Places: cities/attractions visited
- People: travel companions
- Expenses: categorized totals for transportation, tickets, etc.

**Mixed Text & Images**
- Support export to Markdown/HTML
- Ready for publishing to blog platforms
- Support PDF generation

### 3.4 Technical Approach

- Use LangChain/LangGraph to orchestrate the multi-step generation pipeline
- Staged generation: itinerary overview → daily details → expense summary → final polish
- Support streaming output to show generation progress
- Provide a template engine for customizing output formats

### 3.5 Priority

**High** — core differentiating feature

---

## 4. Social Media 9-Grid Generator

### 4.1 Background & Goals

When sharing travel photos on social media, users need to manually collage, select, and caption images. Providing one-click 9-grid generation with accompanying captions lowers the sharing barrier.

### 4.2 Feature Modules

**Smart Photo Selection**
- AI picks 9 most representative photos from the trip
- Considerations: quality score, content diversity, temporal distribution

**Collage Layouts**
- 3x3 standard 9-grid
- Free-form layouts (support irregular layouts such as 1+2+6)
- Style templates: minimal, artistic, vintage

**Caption Generation**
- Generate captions based on photo content and landmarks
- Support multiple styles: poetic, humorous, brief
- Option to add hashtag labels

### 4.3 Technical Approach

- Use Canvas API for collage rendering
- Call large language model for caption generation (few-shot prompts)
- Support preview and fine-tuning

### 4.4 Priority

**High** — strong social sharing appeal

---

## 5. Video Highlight Reel

### 5.1 Background & Goals

Static photos alone cannot fully convey the atmosphere of a trip. Automatically clipping 15-30 second highlight reels from Live Photos and video footage is ideal for sharing on short-video platforms.

### 5.2 Feature Modules

**Footage Collection**
- Support Live Photo video segments
- Support user-uploaded video files
- Support filtering by album/time range

**Smart Editing**
- Automatically identify highlight moments (e.g., smiles, actions, scene transitions)
- Auto-match suitable background music
- Generate multiple duration versions (15s/30s/60s)

**Post-Processing**
- Transition effects (fade in/out, slide)
- Basic color grading
- Add text titles/subtitles

### 5.3 Technical Approach

- Use OpenCV for video analysis (scene detection, optical flow)
- Use FFmpeg for video processing and export
- Or integrate cloud services (e.g., JianYing API)

### 5.4 Priority

**Low** — high technical complexity; can be considered later

---

## 6. Network Folder Scanning

### 6.1 Background & Goals

Users' photos may be scattered across various cloud drives and network storage, such as Baidu Netdisk, Aliyun Drive, OneDrive, SMB shared directories, WebDAV servers, etc. Connecting these data sources enables TrailSnap to uniformly manage and analyze cross-platform photo assets.

### 6.2 Supported Storage Types

**Cloud Drive Services**
| Service | API Type | Notes |
| --- | --- | --- |
| Baidu Netdisk | Open API | Requires applying for an API Key |
| Aliyun Drive | Open API | OAuth2.0 authorization |
| OneDrive | Microsoft Graph API | OAuth2.0 authorization |
| Google Drive | Google Drive API | OAuth2.0 authorization |
| Dropbox | Dropbox API | OAuth2.0 authorization |

**Network File Protocols**
| Protocol | Description | Use Cases |
| --- | --- | --- |
| SMB/CIFS | Common protocol for Windows network shares and NAS | Home NAS, LAN sharing |
| WebDAV | HTTP-based file access protocol | Supported by many NAS and cloud services |
| FTP/SFTP | Traditional file transfer protocols | Legacy system connections |

### 6.3 Feature Modules

**Connection Management**
- Support adding multiple storage accounts
- OAuth2.0 authorization flow (cloud drives)
- Secure storage of account credentials (encrypted)
- Connection status monitoring and auto-reconnection

**File Scanning**
- Recursively scan specified folders
- Scan only image files (jpg, png, heic, raw, etc.)
- Incremental scanning (only new files)
- Scan progress display and interrupt support

**Metadata Extraction**
- File name, path, size, creation/modification time
- EXIF metadata (camera, GPS, timestamp)
- Deduplication against existing photo library (based on file hash)

**Preview & Import**
- Thumbnail preview
- Selective import (by folder, by date range)
- Import mode: index-only (original files stay in place) or copy to local storage

### 6.4 Technical Approach

**Cloud Drive SDKs**
- Baidu Netdisk: [baidupcs-go](https://github.com/qingxinrun/baidupcs-go) or official Python SDK
- Aliyun Drive: custom OAuth2 + API calls
- OneDrive: [Microsoft Graph SDK for Python](https://github.com/microsoftgraph/msgraph-sdk-python)
- Google Drive: [google-api-python-client](https://github.com/google/google-api-python-client)
- Dropbox: [dropbox-sdk-python](https://github.com/dropbox/dropbox-sdk-python)

**Network Protocols**
- SMB: [pysmb](https://github.com/miketeo/pysmb) or [python-smb](https://github.com/miketeo/python-smb)
- WebDAV: [webdavclient3](https://github.com/barneygale/webdavclient3)
- FTP/SFTP: [ftplib](https://docs.python.org/3/library/ftplib.html) / [pysftp](https://github.com/paramiko/pysftp)

**Architecture Design**
```
┌─────────────────────────────────────────┐
│            Storage Adapter Layer         │
│  ┌─────────┐ ┌─────────┐ ┌───────────┐ │
│  │ BaiduPCS│ │ Aliyun  │ │ OneDrive  │ │
│  └─────────┘ └─────────┘ └───────────┘ │
│  ┌─────────┐ ┌─────────┐ ┌───────────┐ │
│  │  SMB    │ │ WebDAV  │ │   SFTP    │ │
│  └─────────┘ └─────────┘ └───────────┘ │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│           Unified File Indexer           │
│  - File listing abstraction layer       │
│  - Deduplication (MD5/SHA256)           │
│  - Metadata normalization               │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│           TrailSnap Photo Store          │
│  - Import photos to local index         │
│  - Or keep metadata reference only      │
└─────────────────────────────────────────┘
```

**Security**
- Cloud drive OAuth tokens stored securely (encrypted before saving to database)
- Network protocol credentials encrypted at rest
- Periodic token refresh
- Least-privilege principle (request read-only access)

### 6.5 Priority

**High** — significantly expands data sources and increases application value

---

## 7. Family Sharing & Collaboration

### 7.1 Background & Goals

Family members may share a single TrailSnap instance or want to share specific albums with each other. Supporting multi-user collaboration scenarios.

### 7.2 Feature Modules

**Permission Management**
- Admin and regular user roles
- Album-level permission control (view, edit, share)
- Guest mode (view-only for designated albums)

**Album Sharing**
- Generate sharing links (optional password protection)
- Expiration control (24 hours / 7 days / permanent)
- Disable download toggle

**Comments & Likes**
- Family members can comment on photos
- Simple like reactions

### 7.3 Technical Approach

- Reuse existing user system, add role fields
- Sharing links use JWT or temporary tokens
- Comments stored in a separate table

### 7.4 Priority

**Low** — multi-user scenarios can be considered later

---

## 8. Smart Album Recommendations

### 8.1 Background & Goals

Users may not proactively create albums. The system can suggest "worth organizing" albums, such as "Weekend Gathering", "National Day Holiday", etc.

### 8.2 Recommendation Scenarios

| Scenario | Trigger Condition |
| --- | --- |
| Weekend Gathering | 5+ photos on Saturday/Sunday, concentrated in one location |
| National Day Holiday | 20+ photos during the National Day holiday |
| Food Collection | 10+ photos in the "Food" category recently |
| Family Moments | Recent photos predominantly tagged "Parents" or "Children" |
| Landmark Check-in | 3+ photos at a 5A scenic spot |

### 8.3 Technical Approach

- Scheduled task scanning, analyzing recent photo distribution
- Generate recommendations based on rules + AI recognition
- Present to user for confirmation before creating albums

### 8.4 Priority

**Medium** — improves user engagement

---

## Priority Summary

| Priority | Features |
| --- | --- |
| **High** | Auto Travel Journal, Social Media 9-Grid, Network Folder Scanning |
| **Medium** | Image Editing, Smart Album Recommendations |
| **Low** | Video Highlight Reel, Family Sharing & Collaboration |
| **Launched** | Photo Auto-Organize |

---

*This document is a design draft. Implementation details may be further refined before formal development. Welcome contributions via Issue or PR.*
