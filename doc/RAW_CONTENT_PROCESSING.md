# Raw Content Processing

## Overview

Raw content processing imports already-downloaded media from WebDAV into the bot's uploader-compatible storage layout.

Current implementation is **grouped-directory only**:

- supported: one directory per post with `metadata.json` or `metadata.txt`
- not supported: legacy flat layouts such as `image.jpg` + `image.jpg.txt`

The feature is exposed through the dedicated **Raw Content** page (`/raw-content`) and the related API endpoints.

## Current data flow

```text
WebDAV source directory
    |
scan_source()
    |
raw_content_queue
    |
process_candidate(mode="grouped")
    |
{dest_dir}/{source}/{username}/
```

## Supported source layout

```text
/raw-content/__extension-ff/
`-- example_shortcode_001/
    |-- metadata.txt
    |-- image_001.jpg
    |-- image_002.jpg
    `-- video_001.mp4
```

Container directories are also supported during scan. If a top-level directory does not contain metadata itself, the scanner looks for nested grouped post directories and expands them into queue items.

## Metadata contract

`metadata.json` and `metadata.txt` are both accepted.

Minimal practical example:

```txt
post_id: example_shortcode_001
username: example.account
caption: Example caption
source: instagram
created_at: 2026-02-20T13:47:46Z
files: [image_001.jpg, image_002.jpg, video_001.mp4]
```

### Field behavior

| Field | Status | Notes |
|---|---|---|
| `post_id` | optional | Falls back to the directory name |
| `source` | optional | Defaults to `instagram` |
| `files` | optional | Auto-detected from files in the post directory when omitted |
| `username` / `post_owner` / `owner` / `author` | effectively required | Processing stops if owner cannot be resolved |
| `caption` | optional | Preserved in `metadata.json` |
| `created_at` | optional | Written to the normalized top-level `metadata.json` |
| `timestamp` | optional | Preserved only inside `raw_metadata` unless an adapter maps it |
| `url` / `post_url` / `link` / `post_link` | optional | Can help owner resolution during scan |

## Processing behavior

### 1. Scan

`scan_source()`:

- lists the source directory
- keeps only grouped directories
- skips standalone files from the old flat format
- reads metadata when present
- stores candidates in `raw_content_queue`

### 2. Process

`process_candidate(..., mode="grouped")`:

1. reads `metadata.json` or `metadata.txt`
2. fills defaults for missing `source` and `post_id`
3. auto-detects media files if `files` is missing
4. validates that a username/owner can be resolved
5. optionally removes exact byte-identical duplicates inside the same post directory
6. moves media files to the destination directory
7. writes normalized `metadata.json`
8. removes source files and cleans up the source directory when possible

## Destination layout

Files are written to:

```text
{dest_dir}/{source}/{username}/
```

Example:

```text
/processed-content/instagram/example.account/
|-- image_001.jpg
|-- image_002.jpg
|-- video_001.mp4
`-- metadata.json
```

### Important current limitation

The destination is **per username, not per post**. If multiple posts from the same account are processed into the same destination:

- media files accumulate in one directory
- `metadata.json` is overwritten by the most recently processed post

This is the current implementation, not a documentation shortcut.

## Web UI

The primary UI is `/raw-content`, not the main dashboard block.

From this page you can:

- scan the source directory
- process queued items in batches
- enable safe dedupe
- clear queue items before rescanning
- override source and destination directories per user

## API endpoints

### `POST /api/raw-content/scan`

Scans the source directory and upserts candidates into `raw_content_queue`.

Useful query/body params:

- `limit`
- `clear_all`
- `new_format_only`

### `POST /api/raw-content/process`

Starts background batch processing for queued items.

Useful query/body params:

- `batch_size`
- `dedupe_before_process`

Typical response:

```json
{
  "status": "processing",
  "message": "Batch processing started (items: 12)",
  "details": {
    "batch_size": 50,
    "queued_items": 12
  }
}
```

### `POST /api/process-raw-content`

Backward-compatible endpoint that:

1. runs a scan
2. processes a single controlled batch
3. returns a summary with `processed_count`, `error_count`, and `remaining_scanned`

Prefer the two-step `/api/raw-content/scan` + `/api/raw-content/process` flow for normal use.

## Metadata written to destination

The generated `metadata.json` currently follows the adapter output:

```json
{
  "post_id": "example_shortcode_001",
  "source": "instagram",
  "username": "example.account",
  "caption": "Example caption",
  "created_at": "2026-02-20T13:47:46Z",
  "media_count": 3,
  "raw_metadata": {
    "post_id": "example_shortcode_001",
    "username": "example.account",
    "caption": "Example caption",
    "source": "instagram",
    "timestamp": "2026-02-20T13:47:46Z",
    "files": ["image_001.jpg", "image_002.jpg", "video_001.mp4"]
  }
}
```

## Related docs

- [FIREFOX_EXTENSION_INTEGRATION.md](FIREFOX_EXTENSION_INTEGRATION.md) - extension-side upload format
- [RAW_CONTENT_INTEGRATION.md](RAW_CONTENT_INTEGRATION.md) - setup checklist
- [RAW_CONTENT_PROCESSING_ALGORITHM.md](RAW_CONTENT_PROCESSING_ALGORITHM.md) - concise maintainer flow
