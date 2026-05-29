# Raw Content Integration Guide

Use this guide to wire the feature into a running instance. For behavior details and API semantics, see [RAW_CONTENT_PROCESSING.md](RAW_CONTENT_PROCESSING.md).

## 1. Enable it in `bot.py`

`WebUI` must receive an uploader plus raw-content directories:

```python
from src.modules.webui import WebUI
from src.modules.uploader import Uploader

uploader = Uploader(database=database, vault=vault)

webui = WebUI(
    database=database,
    vault=vault,
    users={'auth': users_auth, 'rate_limited': users_rl},
    uploader=uploader,
    raw_content_source_dir='/raw-content/__extension-ff',
    raw_content_dest_dir='/processed-content'
)
```

If `uploader` is missing, raw content endpoints return `503` and the UI shows the feature as unavailable.

## 2. Prepare WebDAV directories

Create a source directory for grouped posts and a destination directory for processed output:

```text
/
|-- raw-content/
|   `-- __extension-ff/
|       `-- example_shortcode_001/
|           |-- metadata.txt
|           |-- image_001.jpg
|           `-- image_002.jpg
`-- processed-content/
```

Do not rely on the legacy flat format (`post.json` in the root plus loose media files). The current processor skips that layout.

## 3. Upload grouped post directories

Each post should arrive as its own directory with:

- `metadata.json` or `metadata.txt`
- all referenced media files in the same directory

Minimal example:

```txt
post_id: example_shortcode_001
username: example.account
caption: Example caption
source: instagram
files: [image_001.jpg, image_002.jpg]
```

`metadata.txt` accepts both `key=value` and `key: value` syntax. Arrays must stay in square brackets.

`source` and `post_id` can be inferred, but `username`/owner must still be resolvable or processing will fail.

## 4. Use the Raw Content page

Open `/raw-content` and run the normal flow:

1. **Scan Directory** to discover grouped candidates and fill the queue
2. **Process Batch** to process queued items in the background

Useful options on the page:

- **Clear ALL queue items before scan**: removes prior scanned, completed, and error entries
- **Use new format only**: keeps scan focused on grouped Firefox-extension items
- **Dedupe files before processing**: removes exact byte-identical duplicates inside one post directory
- **Directory Configuration**: saves per-user source and destination overrides

## 5. Verify output

Processed files are written under:

```text
{dest_dir}/{source}/{username}/
```

Example:

```text
/processed-content/instagram/example.account/
|-- image_001.jpg
|-- image_002.jpg
`-- metadata.json
```

Current limitation: multiple posts from the same account share that directory, so `metadata.json` is replaced by the last processed post for that username.

## 6. Recommended API flow

Prefer the dedicated endpoints:

```bash
curl -X POST http://localhost:8080/api/raw-content/scan \
  -H "Cookie: session=<your-session-token>"

curl -X POST "http://localhost:8080/api/raw-content/process?batch_size=50" \
  -H "Cookie: session=<your-session-token>"
```

`POST /api/process-raw-content` still exists, but it is now a compatibility wrapper around scan + one controlled batch.

## 7. Common failures

| Symptom | Likely cause | Fix |
|---|---|---|
| `Raw content processing is not configured on this instance` | `WebUI` was initialized without `uploader` | Pass `uploader` and raw-content directories |
| `No metadata file found in directory ...` | Grouped directory is incomplete | Add `metadata.json` or `metadata.txt` |
| `Missing required username/owner for post ...` | Metadata does not expose an owner | Add `username`, `post_owner`, `owner`, or another resolvable owner field |
| Files are skipped during scan | Source still uses flat legacy layout | Migrate uploads to grouped directories |

## Related docs

- [RAW_CONTENT_PROCESSING.md](RAW_CONTENT_PROCESSING.md)
- [FIREFOX_EXTENSION_INTEGRATION.md](FIREFOX_EXTENSION_INTEGRATION.md)
