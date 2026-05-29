# Raw Content Processing

## Overview

The raw content processing feature allows you to organize and index content that was scraped from external sources (such as browser extensions) into your bot's structured directory system. This is useful when you have content from sources like your Firefox extension that uploads raw files to WebDAV without database indexing.

## Architecture

### Components

1. **ContentProcessor** (base class)
   - Abstract base class for source-specific content processors
   - Defines interface for `fetch_content()`, `organize_content()`, and `save_content()`
   - Extensible for future sources (TikTok, Twitter, etc.)

2. **RawContentProcessor**
   - Processes already-downloaded content stored in WebDAV
   - Handles file organization into structured directories
   - Manages metadata parsing and validation
   - Supports pluggable adapters for different sources

3. **Adapters** (Source-specific implementations)
   - `InstagramRawAdapter` - Handles Instagram metadata from browser extensions
   - Extensible pattern for other sources
   - Each adapter knows how to organize and validate source-specific metadata

### Data Flow

```
Raw Content (WebDAV)
    ↓
RawContentProcessor.process_all()
    ↓
InstagramRawAdapter.organize()
    ↓
Structured directory with metadata.json
```

## Usage

### In Code

```python
from src.modules.content_processor import RawContentProcessor

# Initialize processor
processor = RawContentProcessor(
    webdav_client=uploader.webdav_client,
    source_dir='/raw-content',
    dest_dir='/processed-content',
    database=database
)

# Process all content
result = processor.process_all()

print(f"Processed: {result['processed_count']}")
print(f"Errors: {result['errors']}")
```

### Via Web UI

1. Go to the Dashboard
2. Look for the "🔄 Process Raw Content" section
3. Click "Start Processing"
4. Monitor the progress and view results

### Configuration

When initializing `WebUI`, pass these additional parameters:

```python
webui = WebUI(
    database=database,
    vault=vault,
    users=users,
    uploader=uploader,  # Required for content processing
    raw_content_source_dir='/raw-content',  # WebDAV source directory
    raw_content_dest_dir='/processed-content'  # WebDAV destination directory
)
```

## Output Structure

After processing, files are organized as follows:

```
/processed-content/
├── instagram/
│   ├── 2026-02/
│   │   └── username/
│   │       └── post_id_123/
│   │           ├── image1.jpg
│   │           ├── image2.jpg
│   │           └── metadata.json
│   └── 2026-01/
│       └── another_user/
│           └── post_id_456/
│               ├── video.mp4
│               └── metadata.json
```

### Metadata Format

Each post directory contains a `metadata.json` file:

```json
{
  "post_id": "post_123",
  "source": "instagram",
  "username": "testuser",
  "caption": "Sample caption",
  "created_at": "2026-02-21T10:00:00",
  "media_count": 2,
  "raw_metadata": {
    "post_id": "post_123",
    "username": "testuser",
    "caption": "Sample caption",
    "created_at": "2026-02-21T10:00:00",
    "source": "instagram",
    "files": ["image1.jpg", "image2.jpg"]
  }
}
```

## Input Format (Raw Content)

Your browser extension or script should create metadata files with the following structure:

```json
{
  "post_id": "post_123",
  "username": "testuser",
  "caption": "Sample caption",
  "created_at": "2026-02-21T10:00:00",
  "source": "instagram",
  "files": ["image1.jpg", "image2.jpg"]
}
```

**Required fields:**
- `post_id` - Unique identifier for the post
- `source` - Content source (e.g., "instagram")
- `files` - Array of media file names associated with the post

**Optional fields:**
- `username` - Username of the poster
- `caption` - Post caption/description
- `created_at` - Post creation timestamp (ISO format)

## Adding New Sources

To support a new source (e.g., TikTok), follow these steps:

### 1. Create a New Adapter Class

```python
# In src/modules/content_processor.py

class TiktokRawAdapter:
    """Adapter for processing raw TikTok content."""

    def __init__(self, metadata: Dict[str, Any], webdav_client: object):
        self.metadata = metadata
        self.webdav_client = webdav_client

    def organize(self) -> Dict[str, Any]:
        """Organize TikTok metadata into structured format."""
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

### 2. Register the Adapter

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

## API Endpoint

### Process Raw Content

**POST** `/api/process-raw-content`

**Authentication:** Required (Telegram OAuth)

**Response Codes:**
- `200 OK` - All content processed successfully
- `207 Multi-Status` - Partial success (some items processed, some failed)
- `400 Bad Request` - All items failed
- `503 Service Unavailable` - Feature not configured
- `500 Internal Server Error` - Unexpected error

**Response Format:**

```json
{
  "status": "success|partial|error",
  "message": "Processing complete: X processed, Y skipped, Z errors",
  "details": {
    "processed_count": 10,
    "skipped_count": 2,
    "error_count": 1,
    "processed_items": [
      {
        "post_id": "post_123",
        "source": "instagram",
        "destination": "/processed-content/instagram/2026-02/username/post_123",
        "files_moved": 2
      }
    ],
    "errors": [
      "Error processing file.json: Invalid JSON format"
    ]
  }
}
```

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| "Content processing is not configured" | Uploader not passed to WebUI | Provide `uploader` parameter during WebUI init |
| "Invalid JSON in metadata file" | Malformed JSON in source directory | Ensure files in source directory are valid JSON |
| "Could not move file X" | WebDAV permission or path issue | Check WebDAV credentials and directory permissions |
| "Network error" | Frontend-to-API communication issue | Check network connection and API logs |

## Testing

Run tests for the content processor:

```bash
pytest tests/test_content_processor.py -v
```

## Monitoring

Check logs for processing activity:

```bash
# Look for [RawContentProcessor] and [ContentProcessor] entries
tail -f /var/log/bot.log | grep -i "content"
```

## Future Enhancements

- Database storage of processed metadata for querying
- Batch processing with progress tracking
- Scheduled automatic processing
- Support for more sources (TikTok, YouTube, Twitter)
- Webhook notifications on processing completion
- Metadata editing/organization UI
- Duplicate detection and merging
