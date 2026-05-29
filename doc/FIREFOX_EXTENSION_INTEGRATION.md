# Firefox Extension Integration Guide

This document provides instructions for developing a Firefox extension to capture Instagram content and prepare it for processing by pyinstabot-downloader's Raw Content Processor.

## Target Directory Structure

The extension should save content to a WebDAV directory (e.g., `/raw-content/__extension-ff/`) with the following recommended structure:

### Recommended Structure: Group by Post ID

```
/raw-content/__extension-ff/
├── {POST_ID_1}/
│   ├── metadata.txt           # Single metadata file per post
│   ├── image_001.jpg          # All media files for this post
│   ├── image_002.jpg
│   └── video_001.mp4
├── {POST_ID_2}/
│   ├── metadata.txt
│   └── image_001.jpg
└── {POST_ID_3}/
    ├── metadata.txt
    ├── image_001.jpg
    └── image_002.jpg
```

**Benefits:**
- Natural grouping of carousel posts
- Single metadata file per post (no duplication)
- Easy to extend with additional files
- Clear post boundaries

## Metadata Format

### Format Options

The processor supports both **JSON** and **TXT** formats. Choose based on your preference:

#### Option 1: TXT Format (Recommended for simplicity)

Create a `metadata.txt` file in each post directory:

```txt
post_id: example_shortcode_001
username: example.account
timestamp: 2026-02-20T13:47:46.054Z
url: https://www.instagram.com/p/example_shortcode_001/
caption: Example post caption for documentation
source: instagram
files: [image_001.jpg, image_002.jpg, video_001.mp4]
```

**TXT Format Rules:**
- One field per line in format `Key: Value` or `key=value`
- Arrays use square brackets: `files: [file1.jpg, file2.jpg]`
- Comments start with `#` and are ignored
- Empty lines are ignored
- Keys are case-insensitive and automatically normalized

#### Option 2: JSON Format

Create a `metadata.json` file in each post directory:

```json
{
  "post_id": "example_shortcode_001",
  "username": "example.account",
  "timestamp": "2026-02-20T13:47:46.054Z",
  "url": "https://www.instagram.com/p/example_shortcode_001/",
  "caption": "Example post caption for documentation",
  "source": "instagram",
  "files": [
    "image_001.jpg",
    "image_002.jpg",
    "video_001.mp4"
  ]
}
```

## Required Fields

The following fields are **required** for successful processing:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `post_id` | string | Unique post identifier (shortcode) | `example_shortcode_001` |
| `source` | string | Platform name (lowercase) | `instagram` |
| `files` | array | List of media filenames in the same directory | `["image_001.jpg"]` |

**Note:** If `source` is not provided, it defaults to `instagram`.

## Optional Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `username` | string | Account username | `example.account` |
| `caption` | string | Post caption/description | `"Amazing sunset!"` |
| `timestamp` | string | Post creation time (ISO 8601) | `2026-02-20T13:47:46.054Z` |
| `url` | string | Full post URL | `https://www.instagram.com/p/example_shortcode_001/` |
| `unique_id` | string | Internal extension ID for tracking | `1771595266053_ds221ai0` |
| `original_filename` | string | Original filename before renaming | `example.account__2026-02-18T191021.000Z.jpg` |

## Extension Implementation Workflow

### 1. Content Detection
- Listen for Instagram post page loads
- Extract post metadata from DOM or API calls
- Detect media type (photo, carousel, video, IGTV)

### 2. Media Download
- For single posts: download the image/video
- For carousels: download all media in sequence
- Generate unique filenames (avoid collisions)

### 3. Directory Creation
- Create a subdirectory using the `post_id`
- Example: `/raw-content/__extension-ff/example_shortcode_001/`

### 4. Save Media Files
- Save all downloaded media to the post directory
- Use descriptive but consistent naming:
  - `image_001.jpg`, `image_002.jpg` for photos
  - `video_001.mp4` for videos
  - Or use timestamp-based names: `1771595266053.jpg`

### 5. Generate Metadata File
- Create `metadata.txt` or `metadata.json` in the same directory
- Include all required fields
- Add optional fields when available
- List all media files in the `files` array

### 6. Upload to WebDAV
- Upload the entire post directory to the target WebDAV location
- Ensure atomic operations (upload complete directory or nothing)

## Processing Flow

Once the extension saves content to the WebDAV directory:

1. User triggers processing via WebUI (Dashboard → "🔄 Process Raw Content")
2. Processor scans `/raw-content/__extension-ff/` directories
3. For each post directory:
   - Reads `metadata.txt` or `metadata.json`
   - Validates required fields (`post_id`, `source`, `files`)
   - Moves post directory to structured location: `/processed-content/{source}/{YYYY-MM}/{username}/{post_id}/`
   - Optionally stores metadata in database

## Example: Complete Post Capture

### Step-by-Step for a Carousel Post

**Detected Post:**
- URL: `https://www.instagram.com/p/example_shortcode_001/`
- Username: `example.account`
- Contains 3 images

**Actions by Extension:**

1. Create directory: `/raw-content/__extension-ff/example_shortcode_001/`

2. Download and save media:
   - `/raw-content/__extension-ff/example_shortcode_001/image_001.jpg`
   - `/raw-content/__extension-ff/example_shortcode_001/image_002.jpg`
   - `/raw-content/__extension-ff/example_shortcode_001/image_003.jpg`

3. Create metadata file `/raw-content/__extension-ff/example_shortcode_001/metadata.txt`:
   ```txt
   post_id: example_shortcode_001
   username: example.account
   timestamp: 2026-02-20T13:47:46.000Z
   url: https://www.instagram.com/p/example_shortcode_001/
   caption: Example carousel caption
   source: instagram
   files: [image_001.jpg, image_002.jpg, image_003.jpg]
   ```

4. Result after processing:
   - Destination: `/processed-content/instagram/2026-02/example.account/example_shortcode_001/`
   - All 3 images moved
   - Metadata stored

## Error Handling

The processor will **skip** posts with errors and continue processing others. Common errors:

| Error | Cause | Solution |
|-------|-------|----------|
| `Missing required field 'post_id'` | Metadata missing `post_id` | Ensure `post_id` is always included |
| `No media files found` | `files` array empty or files don't exist | Verify all files in `files` array exist in directory |
| `Invalid metadata format` | Malformed JSON or TXT | Validate format before saving |

## Testing Checklist

Before deploying the extension, verify:

- [ ] Single photo posts are captured correctly
- [ ] Carousel posts include all images in `files` array
- [ ] Video posts download and list video files
- [ ] Metadata includes all required fields (`post_id`, `source`, `files`)
- [ ] Post directory structure matches recommendation
- [ ] Filenames don't contain special characters that break WebDAV
- [ ] `files` array lists filenames (not full paths)
- [ ] All media files referenced in `files` exist in the directory

## Migration from Current Structure

If you already have content in the current structure (one `.txt` per file):

```
# Current structure
1771595266053_ds221ai0.jpg
1771595266053_ds221ai0.jpg.txt
```

The processor **already supports this** through auto-detection:
- It finds `.txt` files
- Auto-detects paired media file (removes `.txt` extension)
- Adds default `source: instagram`
- Processes each file individually

However, **carousels will be split into separate posts**. To fix this, migrate to the grouped structure.

## Support for Future Platforms

When extending to TikTok, YouTube, etc.:

1. Change `source` field to match platform: `tiktok`, `youtube`, `twitter`
2. Use platform-specific `post_id` format
3. Keep the same directory structure
4. Create platform-specific adapters (see `src/modules/content_processor.py`)

## Questions or Issues?

- Check logs: `grep "RawContentProcessor" /var/log/bot.log`
- Validate metadata with online tools (JSON: jsonlint.com, TXT: manual review)
- Ensure WebDAV permissions allow read/write/delete in both source and destination directories

## Additional Resources

- [Raw Content Processing Technical Documentation](RAW_CONTENT_PROCESSING.md)
- [Integration Guide](RAW_CONTENT_INTEGRATION.md)
- [Main README](../README.md#raw-content-processing)
