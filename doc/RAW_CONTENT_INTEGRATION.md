# Integrating Raw Content Processing

## Quick start

### 1. Verify Vault configuration

Make sure the WebDAV uploader configuration is available:

```bash
# Check the Vault entry
vault kv get configuration/uploader-api
```

### 2. Initialize it in `bot.py`

When creating `WebUI`, pass the content-processing settings:

```python
from src.modules.webui import WebUI
from src.modules.uploader import Uploader

# ... your existing code ...

# Initialize the uploader
uploader = Uploader(database=database, vault=vault)

# Pass uploader and content directories into WebUI
webui = WebUI(
    database=database,
    vault=vault,
    users={'auth': users_auth, 'rate_limited': users_rl},
    uploader=uploader,  # NEW: enables content processing
    raw_content_source_dir='/raw-content',  # NEW: raw content source
    raw_content_dest_dir='/processed-content',  # NEW: processed content destination
    # ... other parameters ...
)
```

### 3. Prepare WebDAV directories

Make sure these directories exist in your WebDAV storage:

```text
/
|-- raw-content/          (raw content source)
|   |-- post_123.json     (JSON metadata)
|   |-- post_456.txt      (TXT metadata)
|   |-- image1.jpg
|   |-- image2.jpg
|   `-- ...
`-- processed-content/    (processed content output)
    `-- (filled automatically after processing)
```

## Browser extension metadata format

Your Firefox extension can create metadata files in `/raw-content/` as either **JSON** or **TXT**.

### JSON format

```json
{
  "post_id": "17999999999999999",
  "username": "testuser",
  "caption": "Awesome post caption here",
  "created_at": "2026-02-21T10:30:45",
  "source": "instagram",
  "files": [
    "instagram_17999999999999999_1.jpg",
    "instagram_17999999999999999_2.jpg",
    "instagram_17999999999999999_3.mp4"
  ]
}
```

### TXT format

```txt
post_id=17999999999999999
username=testuser
caption=Awesome post caption here
created_at=2026-02-21T10:30:45
source=instagram
files=[instagram_17999999999999999_1.jpg,instagram_17999999999999999_2.jpg,instagram_17999999999999999_3.mp4]
```

**TXT syntax rules:**
- One parameter per line in `key=value` format
- Arrays use square brackets: `files=[file1.jpg,file2.jpg]`
- Lines starting with `#` are treated as comments
- Empty lines are ignored

**Required fields:**
- `post_id` - unique post identifier
- `source` - source platform (`instagram`, `tiktok`, etc.)
- `files` - list of files that belong to the post

**Optional fields:**
- `username` - account username
- `caption` - post caption or description
- `created_at` - creation time in ISO 8601 format

## Using the Web UI

1. Open **Dashboard** at `/dashboard`.
2. Find the **"🔄 Process Raw Content"** section below the stats blocks.
3. Click **Start Processing**.
4. Review the results summary with processed, skipped, and failed items.

## Using the API

### Start content processing

```bash
curl -X POST http://localhost:8080/api/process-raw-content \
  -H "Cookie: session=<your-session-token>"
```

### Successful response

```json
{
  "status": "success",
  "message": "Processing complete: 5 processed, 2 skipped, 0 errors",
  "details": {
    "processed_count": 5,
    "skipped_count": 2,
    "error_count": 0,
    "processed_items": [
      {
        "post_id": "17999999999999999",
        "source": "instagram",
        "destination": "/processed-content/instagram/2026-02/testuser/17999999999999999",
        "files_moved": 3
      }
    ],
    "errors": []
  }
}
```

## Extending the feature

### Add support for another platform

1. Create an adapter in `src/modules/content_processor.py`:

```python
class TiktokRawAdapter:
    def __init__(self, metadata, webdav_client):
        self.metadata = metadata
        self.webdav_client = webdav_client

    def organize(self):
        return {
            'post_id': self.metadata.get('video_id'),
            'source': 'tiktok',
            'username': self.metadata.get('author'),
            'description': self.metadata.get('description'),
            'created_at': self.metadata.get('created_at'),
            'media_count': len(self.metadata.get('files', [])),
            'raw_metadata': self.metadata
        }
```

2. Register the adapter when initializing `RawContentProcessor`:

```python
processor = RawContentProcessor(
    webdav_client=webdav_client,
    source_dir='/raw-content',
    dest_dir='/processed-content',
    adapter_map={
        'instagram': InstagramRawAdapter,
        'tiktok': TiktokRawAdapter  # New adapter
    }
)
```

## Monitoring and debugging

### Check logs

```bash
# Review content processing logs
grep "RawContentProcessor\|ContentProcessor" /var/log/bot.log

# Review related errors
grep "error\|Error\|ERROR" /var/log/bot.log | grep ContentProcessor
```

### Check WebDAV directories

```bash
# Use your WebDAV client to inspect the directory structure
# Example with curl
curl -X PROPFIND http://webdav.example.com/raw-content/
```

### Debug a specific post

If a post is not processed:

1. Validate the JSON or TXT metadata file.
2. Make sure every file listed in `files` exists in the same directory.
3. Verify WebDAV permissions.
4. Inspect logs for the full error details.

## Common issues

### "Content processing is not configured"

**Cause:** `WebUI` was initialized without the `uploader` argument.

**Fix:**
```python
webui = WebUI(
    # ... other parameters ...
    uploader=uploader,  # Add this
    raw_content_source_dir='/raw-content',
    raw_content_dest_dir='/processed-content'
)
```

### "Invalid metadata format in file"

**Cause:** The browser extension wrote invalid JSON or TXT metadata.

**Fix:**
- For JSON, validate the payload with `jsonlint` or a similar tool.
- For TXT, make sure every line follows `key=value` and arrays use square brackets.

### Files are not moved into the processed directory

**Cause:** WebDAV permission or path mismatch.

**Fix:** Verify that:
- the WebDAV account has read/write access to both directories
- the configured paths match `raw_content_source_dir` and `raw_content_dest_dir`

## Browser extension example

### Firefox extension (JavaScript)

```javascript
// content-script.js
async function scrapeAndUpload() {
    const postId = document.querySelector('[data-testid="post"]').id;
    const username = document.querySelector('a[href="/' + getUsername() + '"]').href.split('/')[3];
    const caption = document.querySelector('[data-testid="post-caption"]').textContent;

    const metadata = {
        post_id: postId,
        username: username,
        caption: caption,
        created_at: new Date().toISOString(),
        source: 'instagram',
        files: [] // filled while media files are downloaded
    };

    // Upload to WebDAV
    const formData = new FormData();
    formData.append('metadata.json', new Blob([JSON.stringify(metadata)], {type: 'application/json'}));
    formData.append('image1.jpg', imageBlob1);
    formData.append('image2.jpg', imageBlob2);

    await fetch('https://webdav.example.com/raw-content/', {
        method: 'POST',
        body: formData
    });
}
```

## Future improvements

Potential follow-up enhancements:
- store metadata in the database for search and filtering
- run processing on a schedule
- add a metadata editing UI
- detect duplicate content
- expose real-time processing progress via WebSocket
- add support for YouTube, TikTok, Twitter, and other platforms
