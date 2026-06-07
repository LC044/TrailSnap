---
outline: [2, 3]
---

# TrailSnap CLI

::: tip
TrailSnap CLI is a command-line tool built on TrailSnap APIs. It can be used directly in your terminal, or as a Skill for Agents.
:::

## 1. Installation

### Install trailsnap-cli

You can install trailsnap-cli in one of three ways:

1. pip

```bash
pip install trailsnap-cli

# Verify installation
trailsnap -v
```

2. npm

```bash
npm install -g trailsnap-cli

# Verify installation
trailsnap -v
```

3. Binary release from GitHub

Download the binary from GitHub Releases and add it to your PATH:  
https://github.com/LC044/TrailSnap/releases

### Using trailsnap-cli

On first use, configure your API URL and Token (replace `<url>` and `<token>` with actual values — see [Token Settings](/en/docs/guide/settings/tokensetting)):

```bash
trailsnap config set --url <url> --token <token>
```

After configuration, verify with a simple query:

```bash
trailsnap photos list --limit 5
```

## 2. Command Reference

::: tip
All commands are run in the terminal using the format `trailsnap <command> <subcommand> [options]`. Commands that interact with the API (photos, locations, etc.) require prior configuration via `config set`, otherwise an error will be shown.
:::

### 2.1 Basic Commands

#### 2.1.1 help — Show help

Displays all available commands, their structure, and core parameters for quick reference.

```bash
trailsnap --help
```

### 2.2 Configuration Commands

#### 2.2.1 config set — Configure API URL and Token

Configures the CLI connection to the backend API, including the API base URL and Bearer token. This is a prerequisite for all API commands.

Format: `config set --url API_URL --token API_TOKEN`

Parameters:

- `--url` (required): API base URL, starting with http/https, e.g. `http://localhost:8000`
- `--token` (required): API access token (Bearer Token) for authentication, obtained from the backend.

Example:

```bash
trailsnap config set --url http://localhost:8000 --token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

On success, the config file path is displayed (written to `.env` in the same directory).

### 2.3 Photo Management Commands

#### 2.3.1 photos — Photo management

Contains three sub-commands: list photos, get photo info, and delete a photo. All sub-commands require prior API configuration.

##### 2.3.1.1 photos list — List photos

Query photos with pagination and filtering by album, location, or device info. Returns a simplified field set.

Format: `photos list [--skip N] [--limit N] [--album-id ID] [--city CITY] [--province PROVINCE] [--make BRAND] [--model MODEL]`

Parameters (can be combined):

- `--skip`: Skip N photos (default 0)
- `--limit`: Return N photos (default 10)
- `--order_by`: Sort field; defaults to memory score. Options: `quality_score`, `memory_score`, `photo_time`
- `--image-type`: Filter by image type, comma-separated. Options: `Camera` (phone/camera), `Screenshot`, `Other`
- `--start-time`: Filter by start time, format: `YYYY-MM-DD HH:MM:SS`
- `--end-time`: Filter by end time, format: `YYYY-MM-DD HH:MM:SS`
- `--album-id`: Filter by album ID, comma-separated
- `--people-id`: Filter by person ID, comma-separated
- `--tag-id`: Filter by tag ID, comma-separated
- `--city`: Filter by city, comma-separated (full name)
- `--province`: Filter by province, comma-separated (full name)
- `--scene`: Filter by scenic spot, comma-separated
- `--make`: Filter by camera brand, comma-separated
- `--model`: Filter by camera model, comma-separated

Returns: JSON array with `id`, `filename`, `file_type`, `photo_time`

Example:

```bash
trailsnap photos list --limit 20 --city "Xi'an,Shanghai"
```

##### 2.3.1.2 photos info — Get photo details

Get metadata and content description for a specific photo.

Format: `photos info --photo-id PHOTO_ID`

Parameters:

- `--photo-id` (required): Unique photo ID, obtainable via `photos list`.

Returns: JSON object containing:

- `address`: Detailed shooting address (down to street level)
- `albums`: Album information
- `tags`: Tag information
- `faces_identities`: Person (face identity) information
- `description`: Photo content description
  - `description`: Photo scene description (empty string if none)
  - `memory_score`: Memory worthiness score (0–100, 100 = most memorable)
  - `quality_score`: Photo quality score (0–100, 100 = highest quality)
  - `narrative`: One-line caption (empty string if none)

Example:

```bash
trailsnap photos info --photo-id 10001
```

##### 2.3.1.3 photos delete — Delete a photo

Delete a specific photo by ID. This action is irreversible — use with caution.

Format: `photos delete --photo-id PHOTO_ID`

Parameters:

- `--photo-id` (required): Unique ID of the photo to delete.

Example:

```bash
trailsnap photos delete --photo-id 10001
```

On success: `Photo <photo-id> deleted successfully`. On failure: `Photo deletion failed or not found`.

### 2.4 Tag Commands

#### 2.4.1 tags list — List classification tags

Query classification tags with pagination.

Format: `tags list [--skip N] [--limit N]`

Parameters:

- `--skip`: Skip N records (default 0)
- `--limit`: Return N records (default 100)

Example:

```bash
trailsnap tags list
```

Returns: JSON array with `id`, `name` (tag_name), `count`.

### 2.5 Album Commands

#### 2.5.1 albums list — List albums

Query albums with pagination.

Format: `albums list [--skip N] [--limit N]`

Parameters:

- `--skip`: Skip N albums (default 0)
- `--limit`: Return N albums (default 100)

Returns: JSON array with `id`, `name`, `count` (num_photos), `description`, `condition`, `type`.

Example:

```bash
trailsnap albums list
```

### 2.6 Location Commands

#### 2.6.1 locations — Location queries

Contains two sub-commands: location distribution and footprint timeline, based on photo GPS data.

##### 2.6.1.1 locations list — Query location distribution

Query location distribution without time info (place name, photo count). Supports grouping by level and date range filtering.

Format: `locations list [--level city|province|district|scene] [--skip N] [--limit N] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]`

Parameters:

- `--level`: Grouping level (default `city`; options: `city`, `province`, `district`, `scene`)
- `--skip`: Skip N locations (default 0)
- `--limit`: Return N locations (default 100)
- `--start-date`: Optional start date (YYYY-MM-DD)
- `--end-date`: Optional end date (YYYY-MM-DD)

Returns: JSON array with `name`, `count`

Example:

```bash
trailsnap locations list
```

##### 2.6.1.2 locations timeline — Footprint timeline

Query footprint timeline grouped by time period and location (start date, end date, location name, photo count). Supports grouping by level and date range filtering.

Format: `locations timeline [--level city|province|district|scene] [--skip N] [--limit N] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]`

Parameters:

- `--level`: Grouping level (default `city`; options: `city`, `province`, `district`, `scene`)
- `--skip`: Skip N locations (default 0)
- `--limit`: Return N locations (default 100)
- `--start-date`: Optional start date (YYYY-MM-DD)
- `--end-date`: Optional end date (YYYY-MM-DD)

Returns: JSON array with `startDate`, `endDate`, `locationName`, `count`

Example:

```bash
trailsnap locations timeline --level city --start-date 2025-01-01 --end-date 2025-06-30
```

### 2.7 People Commands

#### 2.7.1 people list — List recognized people/faces

Query people (face identities) with type filtering.

Format: `people list [--limit N] [--types named,unnamed,hidden]`

Parameters:

- `--limit`: Number of records to return (default 100)
- `--types`: Query types, comma-separated; default `named`. Options: `named`, `unnamed`, `hidden`

Returns: JSON array with `id`, `name` (identity_name), `tags`, `description`, `face_count`.

Example:

```bash
trailsnap people list
```

### 2.8 Folder Commands

#### 2.8.1 folders list — List mounted storage folders

Query information about mounted storage directories.

Format: `folders list`

Returns: JSON output from the backend API (field structure per server response).

Example:

```bash
trailsnap folders list
```

### 2.9 Media Commands

#### 2.9.1 medias get — Get photo media file or URL

Get media content/access URL for a specific photo, supporting URL, base64, or local file output.

Format: `medias get [--photo-id ID] [--size small|medium|large] [--format url|base64|file] [--output FILE_PATH]`

Parameters:

- `--photo-id`: Photo ID (default 100)
- `--size`: Photo quality/size (default `medium`; options: `small`, `medium`, `large`)
- `--format`: Output format (default `url` — can be embedded in HTML/Markdown; options: `url`, `base64`, `file`)
- `--output`: Output file path (required only when `--format file`)

Example:

```bash
# Output URL (large = original image URL; small/medium = thumbnail URL)
trailsnap medias get --photo-id 10001 --format url --size large

# Base64 output (thumbnail base64 encoding)
trailsnap medias get --photo-id 10001 --format base64 --size medium

# Save to local file
trailsnap medias get --photo-id 10001 --format file --output ./photo_10001.jpg
```

### 2.10 Notes

- All API-interacting commands (photos, locations, people, etc.) require prior `config set` with API URL and Token. Otherwise, the error message `Error: API URL and Token not configured. Please run 'config' first.` will be shown.
- All commands support `--help` for detailed usage. Invalid parameters will show specific error messages and the correct format.
