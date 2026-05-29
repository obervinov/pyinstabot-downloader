# Raw Content Processing Algorithm

This note is the short maintainer-oriented version of the current flow. It describes what the code does today, not the originally planned design.

For setup and operator usage, see [RAW_CONTENT_INTEGRATION.md](RAW_CONTENT_INTEGRATION.md). For the user-facing behavior and API reference, see [RAW_CONTENT_PROCESSING.md](RAW_CONTENT_PROCESSING.md).

## Current algorithm

### 1. Scan source storage

`RawContentProcessor.scan_source()`:

1. lists the configured source directory
2. keeps only directories
3. looks for `metadata.json` or `metadata.txt`
4. expands nested grouped directories when the top-level directory is only a container
5. stores discovered candidates in `raw_content_queue`

Standalone metadata files and loose media files are not treated as processable items anymore.

### 2. Build the processing queue

Each queued candidate includes:

- `item_name`
- `item_path`
- `mode='grouped'`
- `post_id`
- `post_owner`
- `source`
- `content_files_json`
- `requires_username`

`requires_username` is set when scan cannot resolve an owner from the metadata.

### 3. Process one queued candidate

`process_candidate()` accepts only `mode='grouped'` and delegates to `_process_grouped_post()`.

Per item, processing does the following:

1. read `metadata.json` or `metadata.txt`
2. parse metadata into a dict
3. use queue-provided `content_files` when available
4. otherwise auto-detect media files from the directory contents
5. default `source` to `instagram` when missing
6. default `post_id` to the directory name when missing
7. resolve owner from metadata and fail if it is still missing
8. optionally dedupe byte-identical files inside the same post directory

### 4. Compute destination path

`_create_destination_path()` writes to:

```text
{dest_dir}/{source}/{username}
```

If `dest_dir` already ends with the source segment, the source is not duplicated.

Example:

```text
dest_dir=/processed-content
source=instagram
username=example.account

-> /processed-content/instagram/example.account
```

### 5. Move files and write metadata

For each file in `files`:

1. download from WebDAV with `download_from()`
2. upload to destination with `upload_to()`
3. remove the source copy with `clean()`

After file moves complete, `_save_metadata()` writes a normalized `metadata.json` into the destination directory.

### 6. Cleanup

After successful grouped processing, the processor:

- removes the source metadata file
- tries to remove the now-empty source post directory

Cleanup failures are logged, but they do not retroactively turn a successful move into an error.

## Current caveats

### Destination is per username, not per post

Multiple posts from the same source account share the same destination directory. That means:

- media files from several posts can coexist in one directory
- `metadata.json` is overwritten by the latest processed post

### Dedupe is intentionally conservative

`_safe_dedupe_grouped_files()` removes only exact byte-identical duplicates inside one grouped post. If hashing or cleanup fails, the file is kept and moved to avoid data loss.

### Legacy single-file mode is no longer part of the active flow

Some old helpers and tests still mention the previous layout, but:

- `process_candidate()` rejects any mode other than `grouped`
- `process_all()` skips non-directory items
- operator-facing docs should not describe flat per-file sidecar processing as supported behavior
