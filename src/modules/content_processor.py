"""
Content Processing Module

This module is responsible for processing content from various sources (Instagram, etc.)
and organizing raw content (e.g., from browser extensions or scripts) into structured directories.
It supports pluggable adapters for different content sources and provides a unified interface.

Examples:
    Process raw content from WebDAV directory:
    >>> processor = RawContentProcessor(
    ...     webdav_client=webdav_client,
    ...     source_dir='/raw-content',
    ...     dest_dir='/processed-content'
    ... )
    >>> result = processor.process_all()
    >>> print(result['processed_count'], result['errors'])
"""

import json
import io
import re
import time
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional, Any, Callable
import requests
import webdav3.exceptions
from webdav3.urn import Urn
from logger import log

# WebDAV operations are retried on transient failures: the server reporting the resource as
# locked (Nextcloud returns 423 under concurrent access) and network hiccups (read timeouts,
# dropped connections) which are common against a busy Nextcloud behind a k8s service.
WEBDAV_RETRY_ATTEMPTS = 3
WEBDAV_RETRY_BACKOFF_SECONDS = 2.0
WEBDAV_TRANSIENT_ERRORS = (
    webdav3.exceptions.ResourceLocked,
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
)
# HTTP status codes worth retrying. 403 is included on purpose: on this Nextcloud a MOVE can
# transiently fail with Sabre\DAV\Exception\Forbidden (empty message) when the same node is being
# touched concurrently (e.g. the desktop sync client walking the source folder) — the identical
# operation succeeds on a later attempt. A genuinely-forbidden op just exhausts the retries.
WEBDAV_TRANSIENT_HTTP_CODES = {403, 409, 423, 429, 500, 502, 503, 504}

# Dedupe fingerprint tuning. Files up to DEDUPE_FULL_HASH_MAX_BYTES are hashed in FULL in a single
# request (cheap for the small media this bot handles, and byte-exact). Larger files fall back to a
# DEDUPE_HEAD_BYTES-sized ranged fingerprint so we never download huge media just to compare.
DEDUPE_HEAD_BYTES = 64 * 1024
DEDUPE_FULL_HASH_MAX_BYTES = 8 * 1024 * 1024
# Concurrency for hashing files within a single post during dedupe. These are read-only GETs
# (shared locks, low contention), so they parallelise safely even when posts run serially.
DEDUPE_HASH_WORKERS = 8

# Concurrency for probing directories during a scan. Each worker holds its own WebDAV client;
# kept modest so Nextcloud is not flooded with parallel PROPFIND/GET requests.
SCAN_MAX_WORKERS = 8


class ContentProcessor:
    """
    Base class for content processors.
    Defines the interface for processing content from various sources.
    """

    def __init__(self, source_config: Dict[str, Any]):
        """
        Initialize the content processor.

        Args:
            source_config: Configuration dict for the content source.
        """
        self.source_config = source_config

    def fetch_content(self) -> Any:
        """
        Fetch content from the configured source.
        Should be overridden by subclasses.

        Raises:
            NotImplementedError: This method must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses should implement this method")

    def organize_content(self, raw_data: Any) -> Dict[str, Any]:
        """
        Organize fetched content into a structured format.

        Args:
            raw_data: Raw data fetched from the source.

        Returns:
            Structured content dict.
        """
        raise NotImplementedError("Subclasses should implement this method")

    def save_content(self, structured_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save organized content to the appropriate location.

        Args:
            structured_data: The organized content to save.

        Returns:
            Result dict with status and details.
        """
        raise NotImplementedError("Subclasses should implement this method")


class RawContentProcessor:
    """
    Processes raw content from WebDAV (e.g., from browser extensions).
    Organizes files into structured directories and optionally saves metadata to database.
    """

    def __init__(self, webdav_client: object, source_dir: str, dest_dir: str, database: Optional[object] = None, **kwargs):
        """
        Initialize the raw content processor.

        Args:
            webdav_client: WebDAV client instance for file operations.
            source_dir: Source directory in WebDAV containing raw content.
            dest_dir: Destination directory in WebDAV for organized content.
            database: Optional database client for storing metadata.
            **kwargs: Additional configuration options.
                adapter_map: Mapping of source name -> raw adapter class.
                client_factory: Optional callable returning a fresh WebDAV client with its own
                    requests.Session. Required to enable parallel processing (webdav3's client is
                    not thread-safe); when absent, parallel processing falls back to serial.
        """
        self.webdav_client = webdav_client
        self.source_dir = source_dir
        self.dest_dir = dest_dir
        self.database = database
        self.adapter_map = kwargs.get('adapter_map', {'instagram': InstagramRawAdapter})
        self.client_factory: Optional[Callable[[], object]] = kwargs.get('client_factory')
        log.info('[RawContentProcessor]: Initialized with source=%s, dest=%s', source_dir, dest_dir)

    @staticmethod
    def _normalize_webdav_name(item: Any) -> str:
        """
        Normalize WebDAV list item to plain filename.

        Supports both list formats:
        - 'filename.ext'
        - {'name': 'filename.ext'}  (list())
        - {'name': ..., 'path': ...}  (list(get_info=True))
        - '/path/to/filename.ext/'

        For get_info=True entries 'name' comes from <d:displayname>, which Nextcloud often leaves
        empty; in that case fall back to 'path' (derived from the response href) which is always set.
        """
        if isinstance(item, dict):
            raw_name = str(item.get('name') or '').strip()
            if not raw_name:
                raw_name = str(item.get('path') or '')
        else:
            raw_name = str(item)

        # Strip trailing slash and keep basename only
        result = raw_name.rstrip('/').split('/')[-1]
        if not result:
            log.debug('[RawContentProcessor]: _normalize returned empty string from: %s', str(item))
        return result

    @staticmethod
    def _raw_item_is_dir(item: Any) -> Optional[bool]:
        """
        Extract the directory flag from a raw WebDAV list() entry without any extra request.

        webdav3's list() already encodes directories: with get_info=True each entry is a dict
        carrying 'isdir', otherwise directory names come back with a trailing slash. Reusing that
        signal avoids a per-item info()/list() round trip against the server.

        Returns:
            True/False when the entry is self-describing, None when it cannot be determined.
        """
        if isinstance(item, dict):
            isdir = item.get('isdir')
            if isinstance(isdir, bool):
                return isdir
            raw_name = str(item.get('name', ''))
        else:
            raw_name = str(item)
        if not raw_name:
            return None
        return raw_name.rstrip('/') != raw_name

    def _is_directory(self, file_path: str, file_name: str, is_dir_hint: Optional[bool] = None) -> bool:
        """
        Best-effort check if a WebDAV path points to a directory.

        Prefers the cheap signals (a hint captured from the parent list() plus extension
        heuristics) and only falls back to a single list() probe when nothing else decides.
        The previous per-item info() call was removed - it cost one HTTP round trip for every
        entry and the same information is already available from the parent listing.

        Args:
            file_path: Full WebDAV path to the entry.
            file_name: Basename of the entry.
            is_dir_hint: Directory flag taken from the parent list() entry, if known.
        """
        # Metadata files should always be treated as files (old structure)
        if file_name.endswith('.json') or file_name.endswith('.txt'):
            log.debug('[RawContentProcessor]: %s is metadata file, not a directory', file_name)
            return False

        # Media files should never be treated as directories
        media_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mov', '.avi', '.webp', '.heic')
        if file_name.lower().endswith(media_extensions):
            log.debug('[RawContentProcessor]: %s has media extension (not a directory)', file_name)
            return False

        # If it has any dot extension at all, it's likely a file, not a directory
        if '.' in file_name and not file_name.startswith('.'):
            log.debug('[RawContentProcessor]: %s has file extension (not a directory)', file_name)
            return False

        # Trust the hint captured from the parent listing (no extra request).
        if is_dir_hint is not None:
            log.debug('[RawContentProcessor]: %s directory flag from parent listing: %s', file_name, is_dir_hint)
            return is_dir_hint

        # Fallback: single list() probe (if we can list it, it's a directory)
        try:
            items = self.webdav_client.list(file_path)
            if items:
                log.debug('[RawContentProcessor]: list() succeeded for %s - treating as directory', file_name)
                return True
        except Exception as list_error:
            log.debug('[RawContentProcessor]: list() failed for %s: %s', file_name, str(list_error))

        # Default assumption: if it has no extension and other checks didn't exclude it, likely a directory
        log.debug('[RawContentProcessor]: %s has no extension - assuming it is a directory', file_name)
        return True

    @staticmethod
    def _with_retry(operation: Callable[[], Any], description: str) -> Any:
        """
        Run a WebDAV operation, retrying on transient failures with linear backoff.

        Retries on Nextcloud resource locks (423 under concurrent access) and network hiccups
        (read timeouts, dropped connections) that are common against a busy Nextcloud. Any other
        error propagates immediately. After the last attempt the original exception is re-raised.

        Args:
            operation: Zero-arg callable performing the WebDAV request.
            description: Human-readable label for logging.
        """
        attempt = 0
        while True:
            try:
                return operation()
            except Exception as err:  # pylint: disable=broad-exception-caught
                transient = isinstance(err, WEBDAV_TRANSIENT_ERRORS) or (
                    isinstance(err, webdav3.exceptions.ResponseErrorCode)
                    and err.code in WEBDAV_TRANSIENT_HTTP_CODES
                )
                if not transient:
                    raise
                attempt += 1
                if attempt > WEBDAV_RETRY_ATTEMPTS:
                    raise
                backoff = WEBDAV_RETRY_BACKOFF_SECONDS * attempt
                log.warning(
                    '[RawContentProcessor]: %s failed transiently (%s: %s), retry %d/%d after %.1fs',
                    description, type(err).__name__, str(err),
                    attempt, WEBDAV_RETRY_ATTEMPTS, backoff
                )
                time.sleep(backoff)

    def _ensure_remote_dir(self, remote_dir: str) -> None:
        """
        Create a remote directory idempotently.

        Safe under concurrency: a directory already created by another worker (MKCOL returns
        405 MethodNotSupported / already-exists) is treated as success rather than an error.
        """
        try:
            if self.webdav_client.check(remote_dir):
                return
        except Exception as check_error:
            log.debug('[RawContentProcessor]: check(%s) failed, will try mkdir: %s', remote_dir, str(check_error))
        try:
            self._with_retry(lambda: self.webdav_client.mkdir(remote_dir), f"mkdir {remote_dir}")
        except webdav3.exceptions.MethodNotSupported:
            log.debug('[RawContentProcessor]: mkdir(%s) reports already exists - ok', remote_dir)
        except Exception as mkdir_error:
            # A concurrent worker may have created it between check() and mkdir().
            if self.webdav_client.check(remote_dir):
                log.debug('[RawContentProcessor]: %s appeared concurrently - ok', remote_dir)
            else:
                raise mkdir_error

    def _reconcile_content_files(self, parsed_files: list, content_files: list, label: str) -> list:
        """
        Reconcile the file list declared in metadata with the files actually present in the directory.

        Mirrors the original scan behavior: when counts/names disagree the actual directory files
        win; when they agree the metadata order is used. Returns the list of content files to record.
        """
        if not parsed_files:
            return content_files
        parsed_set = {f for f in parsed_files if f}
        if not parsed_set:
            return content_files

        if len(parsed_set) != len(content_files):
            log.warning(
                '[RawContentProcessor]: [%s] File count mismatch: metadata has %d files, directory has %d files. '
                'Using actual directory files. Metadata: %s | Directory: %s',
                label, len(parsed_set), len(content_files), list(parsed_set), content_files
            )
            return content_files

        filtered_files = [f for f in content_files if f in parsed_set]
        if len(filtered_files) == len(content_files):
            log.debug('[RawContentProcessor]: [%s] File count verified: %d files match metadata', label, len(filtered_files))
            return filtered_files

        log.warning(
            '[RawContentProcessor]: [%s] File name mismatch: metadata names don\'t match directory. '
            'Using actual directory files. Metadata: %s | Directory: %s',
            label, list(parsed_set), content_files
        )
        return content_files

    def _candidate_from_metadata(
        self,
        item_name: str,
        item_path: str,
        metadata: Dict[str, Any],
        content_files: list
    ) -> Dict[str, Any]:
        """Build a processable-candidate dict from parsed metadata and reconciled content files."""
        post_owner = self._resolve_owner(metadata)
        requires_username = not post_owner or not str(post_owner).strip()
        if requires_username:
            log.warning(
                '[RawContentProcessor]: [%s] MISSING USERNAME/OWNER - post will require explicit username before processing. '
                'Metadata keys checked: username=%s, post_owner=%s, owner=%s',
                item_name, metadata.get('username'), metadata.get('post_owner'), metadata.get('owner')
            )
        parsed_files = metadata.get('files') or []
        if isinstance(parsed_files, str):
            parsed_files = [parsed_files]
        content_files = self._reconcile_content_files(parsed_files, content_files, item_name)
        return {
            'item_name': item_name,
            'item_path': item_path,
            'mode': 'grouped',
            'post_id': metadata.get('post_id') or item_name,
            'post_url': (
                metadata.get('post_url') or metadata.get('url')
                or metadata.get('link') or metadata.get('post_link')
            ),
            'post_owner': post_owner,
            'source': (metadata.get('source') or 'instagram').lower(),
            'content_files_json': json.dumps(content_files),
            'requires_username': requires_username
        }

    def _read_metadata(self, client: Any, remote_path: str, filename: str) -> Dict[str, Any]:
        """Download and parse a metadata file using the given WebDAV client."""
        metadata_buffer = io.BytesIO()
        client.download_from(buff=metadata_buffer, remote_path=remote_path)
        metadata_content = metadata_buffer.getvalue().decode('utf-8', errors='ignore')
        return self._parse_metadata(metadata_content, filename)

    def _scan_directory(self, source_dir: str, file_name: str, client: Any) -> Dict[str, Any]:
        """
        Probe one directory under source_dir and return grouped candidates.

        Does the WebDAV listing (+ metadata reads) for a single directory. Extracted so many
        directories can be probed concurrently, each with its own client.

        Returns:
            {'candidates': [<candidate dict>...], 'skipped': int}
            - a direct grouped post yields one candidate,
            - a container of posts yields several,
            - a directory with no metadata anywhere yields none (skipped=1).
        """
        file_path = f"{source_dir}/{file_name}"
        out: Dict[str, Any] = {'candidates': [], 'skipped': 0}
        content_files: list = []
        metadata_file = None
        nested_added = 0
        try:
            items_in_dir = client.list(file_path)
            if items_in_dir:
                for item in items_in_dir:
                    fname = self._normalize_webdav_name(item)
                    if not fname or fname == file_name:
                        continue
                    if fname in ('metadata.json', 'metadata.txt'):
                        metadata_file = fname
                        continue
                    if not fname.endswith(('.json', '.txt')):
                        content_files.append(fname)

            # Container directory support (e.g. __extension-ff/<post-id>): if there is no metadata
            # at this level, treat nested directories as real grouped posts.
            if items_in_dir and not metadata_file:
                for item in items_in_dir:
                    nested_name = self._normalize_webdav_name(item)
                    if not nested_name:
                        continue
                    nested_path = f"{file_path}/{nested_name}"
                    if not self._is_directory(
                        file_path=nested_path,
                        file_name=nested_name,
                        is_dir_hint=self._raw_item_is_dir(item)
                    ):
                        continue

                    nested_files = client.list(nested_path)
                    nested_metadata_file = None
                    nested_content_files = []
                    if nested_files:
                        for nested_item in nested_files:
                            nname = self._normalize_webdav_name(nested_item)
                            if not nname or nname == nested_name:
                                continue
                            if nname in ('metadata.json', 'metadata.txt'):
                                nested_metadata_file = nname
                                continue
                            if not nname.endswith(('.json', '.txt')):
                                nested_content_files.append(nname)

                    if not nested_metadata_file:
                        continue

                    metadata = self._read_metadata(client, f"{nested_path}/{nested_metadata_file}", nested_metadata_file)
                    out['candidates'].append(
                        self._candidate_from_metadata(nested_name, nested_path, metadata, nested_content_files)
                    )
                    nested_added += 1

                if nested_added > 0:
                    log.info('[RawContentProcessor]: Container directory %s expanded into %d grouped candidates', file_name, nested_added)
                    return out

            if metadata_file:
                metadata = self._read_metadata(client, f"{file_path}/{metadata_file}", metadata_file)
                out['candidates'].append(
                    self._candidate_from_metadata(file_name, file_path, metadata, content_files)
                )
                return out
        except Exception as scan_error:
            log.warning('[RawContentProcessor]: Failed to probe directory %s: %s', file_name, str(scan_error))

        # No metadata at this level and no nested posts -> container/empty directory, skip.
        out['skipped'] += 1
        return out

    def scan_source(
        self,
        limit: int = 500,
        offset: int = 0,
        user_id: Optional[str] = None,
        database: Optional[object] = None,
        new_format_only: bool = False,
        source_dir_override: Optional[str] = None,
        dest_dir_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Scan source directory and return processable candidates without processing files.

        IMPORTANT: When user_id and database are provided, items with status='completed'
        will be excluded from results, ensuring scanLimit applies only to NEW items.

        IMPORTANT: The limit applies to the number of PROCESSABLE items returned, not raw items.
        Skipped items (containers, files without metadata, etc.) don't count toward the limit.

        Args:
            limit: Maximum number of NEW (not completed) PROCESSABLE items to return.
            offset: Offset in processable items (applied after filtering completed items and skipped items).
            user_id: User ID to filter completed items (optional).
            database: Database client to query completed items (optional).
            new_format_only: Deprecated parameter, kept for backward compatibility. Only grouped format is supported.
            source_dir_override: Override source directory for this scan (e.g., from user config).
            dest_dir_override: Override destination directory for this scan (e.g., from user config).

        Returns:
            Dict with scan counters and candidate items.
        """
        result = {
            'status': 'success',
            'total_items': 0,
            'scanned_items': 0,
            'processable_count': 0,
            'skipped_count': 0,
            'processable_items': [],
            'errors': []
        }

        # Use overrides if provided, otherwise use instance defaults
        source_dir = source_dir_override or self.source_dir
        dest_dir = dest_dir_override or self.dest_dir

        log.info('[RawContentProcessor]: Starting scan of source_dir=%s (limit=%d, offset=%d, user_id=%s, new_format_only=%s)',
                 source_dir, limit, offset, user_id or 'none', new_format_only)
        try:
            # Get completed paths if user_id provided
            completed_paths = set()
            if user_id and database:
                log.debug('[RawContentProcessor]: Fetching completed paths for user %s', user_id)
                completed_paths = database.get_completed_raw_content_paths(user_id)
                log.debug('[RawContentProcessor]: Found %d completed paths', len(completed_paths))

            log.debug('[RawContentProcessor]: Listing items in source directory')
            raw_items = self.webdav_client.list(source_dir)
            log.debug('[RawContentProcessor]: WebDAV returned %d raw items', len(raw_items))

            # Capture the directory flag from the listing itself (trailing slash / isdir) so we
            # don't have to probe each entry with a separate info()/list() request later.
            dir_hints: Dict[str, Optional[bool]] = {}
            normalized_items = []
            for item in raw_items:
                name = self._normalize_webdav_name(item)
                if not name:
                    continue
                normalized_items.append(name)
                dir_hints[name] = self._raw_item_is_dir(item)
            result['total_items'] = len(normalized_items)
            log.debug('[RawContentProcessor]: After normalization: %d valid items', result['total_items'])

            # NOTE: We scan ALL items first to get processable candidates,
            # then apply offset/limit AFTER filtering to ensure consistent pagination.
            result['scanned_items'] = len(normalized_items)

            # Cheap pre-filter (no network): drop already-completed items and non-directories
            # BEFORE the expensive WebDAV probing, so only genuinely new post directories are probed.
            dirs_to_probe = []
            for file_name in normalized_items:
                file_path = f"{source_dir}/{file_name}"
                if file_path in completed_paths:
                    result['skipped_count'] += 1
                    continue
                if not self._is_directory(file_path=file_path, file_name=file_name, is_dir_hint=dir_hints.get(file_name)):
                    result['skipped_count'] += 1
                    continue
                dirs_to_probe.append(file_name)

            # Probe directories concurrently: the previous serial 1 list + 1 metadata GET per post
            # dominated scan time. Each worker gets its own WebDAV client (webdav3 is not
            # thread-safe); falls back to serial when no client_factory is configured.
            workers = 1
            if self.client_factory and len(dirs_to_probe) > 1:
                workers = min(SCAN_MAX_WORKERS, len(dirs_to_probe))
            log.info('[RawContentProcessor]: Probing %d new director(ies) with %d worker(s)', len(dirs_to_probe), workers)

            def _probe(file_name: str) -> Dict[str, Any]:
                client = self.client_factory() if workers > 1 else self.webdav_client
                return self._scan_directory(source_dir, file_name, client)

            scan_outputs: list = [None] * len(dirs_to_probe)
            if workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    future_to_index = {executor.submit(_probe, name): i for i, name in enumerate(dirs_to_probe)}
                    for future in as_completed(future_to_index):
                        idx = future_to_index[future]
                        try:
                            scan_outputs[idx] = future.result()
                        except Exception as probe_error:  # pylint: disable=broad-exception-caught
                            log.error('[RawContentProcessor]: Probe crashed for %s: %s', dirs_to_probe[idx], str(probe_error))
            else:
                for i, name in enumerate(dirs_to_probe):
                    scan_outputs[i] = _probe(name)

            # Assemble candidates preserving the source listing order.
            for output in scan_outputs:
                if not output:
                    result['skipped_count'] += 1
                    continue
                result['processable_items'].extend(output.get('candidates', []))
                result['skipped_count'] += output.get('skipped', 0)

            # Apply offset/limit to processable items AFTER filtering
            all_processable = result['processable_items']
            result['processable_count'] = len(all_processable)

            # Apply pagination to processable items
            paged_processable = all_processable[offset:offset + limit]
            result['processable_items'] = paged_processable

            log.info(
                '[RawContentProcessor]: Scan complete - total=%d, scanned=%d, all_processable=%d, returned=%d, skipped=%d, completed_excluded=%d',
                result['total_items'],
                result['scanned_items'],
                result['processable_count'],
                len(paged_processable),
                result['skipped_count'],
                len(completed_paths)
            )
            return result
        except Exception as e:
            error_msg = f"Failed to scan source directory: {str(e)}"
            log.error('[RawContentProcessor]: %s', error_msg)
            result['status'] = 'error'
            result['errors'].append(error_msg)
            return result

    def process_candidate(
        self,
        item_path: str,
        item_name: str,
        mode: str,
        content_files: list[str] | None = None,
        post_owner: str | None = None,
        post_id: str | None = None,
        source: str | None = None,
        source_dir_override: str | None = None,
        dest_dir_override: str | None = None,
        dedupe_before_process: bool = True
    ) -> Dict[str, Any]:
        """
        Process single candidate discovered by scan_source().

        Args:
            item_path: Full source path.
            item_name: Item name (directory).
            mode: Must be 'grouped' (legacy 'single' mode is no longer supported).
            content_files: List of content files from database scan (optional).
                If provided, uses these files instead of auto-detecting.
            post_owner: Owner/username from the DB row; when set, metadata is not re-read for it.
            post_id: Post id from the DB row (defaults to item_name).
            source: Source from the DB row (defaults to 'instagram').
            source_dir_override: Optional source directory override for this processing call.
            dest_dir_override: Optional destination directory override for this processing call.
            dedupe_before_process: If True, remove byte-identical duplicates before moving files.
        """
        if mode != 'grouped':
            return {
                'status': 'error',
                'error': f"Unsupported processing mode: {mode}. Only 'grouped' mode is supported."
            }

        return self._process_grouped_post(
            item_path,
            item_name,
            content_files=content_files,
            post_owner=post_owner,
            post_id=post_id,
            source=source,
            dest_dir_override=dest_dir_override,
            dedupe_before_process=dedupe_before_process
        )

    def _make_worker(self) -> "RawContentProcessor":
        """
        Build a lightweight processor bound to its own WebDAV client for use in a worker thread.

        webdav3's client is not thread-safe (shared requests.Session), so each concurrent worker
        must own its client. Falls back to sharing self when no client_factory is configured -
        callers must then keep concurrency at 1.
        """
        if not self.client_factory:
            return self
        worker = RawContentProcessor(
            webdav_client=self.client_factory(),
            source_dir=self.source_dir,
            dest_dir=self.dest_dir,
            adapter_map=self.adapter_map,
        )
        return worker

    def process_candidates_parallel(
        self,
        candidates: list[dict],
        max_workers: int = 4,
        dest_dir_override: str | None = None,
        dedupe_before_process: bool = True,
        on_result: Optional[Callable[[dict], None]] = None
    ) -> list[dict]:
        """
        Process several grouped candidates concurrently, one worker (and one WebDAV client) per thread.

        This does NOT touch the database - callers keep DB status updates on the main thread
        (psycopg connections are not thread-safe). Results are returned in the same order as the
        input candidates so the caller can pair them back with its DB rows.

        Args:
            candidates: List of dicts, each with keys item_path, item_name, mode and optional content_files.
            max_workers: Upper bound on concurrent workers. Kept modest by default so Nextcloud is
                not flooded with parallel WebDAV requests; forced to 1 when no client_factory exists.
            dest_dir_override: Optional destination directory override applied to every candidate.
            dedupe_before_process: If True, dedupe byte-identical files before moving.
            on_result: Optional callback invoked with each {'candidate', 'result'} entry as soon as
                that candidate finishes, so callers can persist progress per item instead of waiting
                for the whole batch. Called from a worker thread - it must be thread-safe and must
                not touch the database directly. Exactly one call per candidate is guaranteed.

        Returns:
            List of {'candidate': <input dict>, 'result': <process_candidate result>} in input order.
        """
        if not candidates:
            return []

        effective_workers = max(1, min(max_workers, len(candidates)))
        if not self.client_factory:
            log.warning(
                '[RawContentProcessor]: No client_factory configured - falling back to serial processing '
                '(webdav3 client is not thread-safe)'
            )
            effective_workers = 1

        log.info(
            '[RawContentProcessor]: Processing %d candidates with %d worker(s)',
            len(candidates), effective_workers
        )

        def _report(entry: dict) -> dict:
            if on_result:
                try:
                    on_result(entry)
                except Exception as callback_error:  # pylint: disable=broad-exception-caught
                    log.error('[RawContentProcessor]: on_result callback failed: %s', str(callback_error))
            return entry

        def _run(candidate: dict) -> dict:
            worker = self._make_worker()
            result = worker.process_candidate(
                item_path=candidate['item_path'],
                item_name=candidate['item_name'],
                mode=candidate.get('mode', 'grouped'),
                content_files=candidate.get('content_files'),
                post_owner=candidate.get('post_owner'),
                post_id=candidate.get('post_id'),
                source=candidate.get('source'),
                dest_dir_override=dest_dir_override,
                dedupe_before_process=dedupe_before_process
            )
            return {'candidate': candidate, 'result': result}

        def _run_guarded(candidate: dict) -> dict:
            try:
                return _run(candidate)
            except Exception as worker_error:  # pylint: disable=broad-exception-caught
                log.error(
                    '[RawContentProcessor]: Worker crashed for %s: %s',
                    candidate.get('item_name'), str(worker_error)
                )
                return {
                    'candidate': candidate,
                    'result': {'status': 'error', 'error': f"Worker crashed: {worker_error}"}
                }

        if effective_workers == 1:
            return [_report(_run_guarded(candidate)) for candidate in candidates]

        results: list[Optional[dict]] = [None] * len(candidates)
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            future_to_index = {
                executor.submit(_run_guarded, candidate): idx
                for idx, candidate in enumerate(candidates)
            }
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                results[idx] = _report(future.result())
        return results

    def process_all(self) -> Dict[str, Any]:
        """
        Process all raw content in the source directory.

        Returns:
            Result dict with statistics and error details.
        """
        result = {
            'status': 'success',
            'processed_count': 0,
            'skipped_count': 0,
            'error_count': 0,
            'errors': [],
            'processed_items': []
        }

        try:
            # List files in source directory
            files = self.webdav_client.list(self.source_dir)
            dir_hints = {}
            normalized_files = []
            for item in files:
                name = self._normalize_webdav_name(item)
                if not name:
                    continue
                normalized_files.append(name)
                dir_hints[name] = self._raw_item_is_dir(item)
            log.info('[RawContentProcessor]: Found %d items in source directory', len(normalized_files))

            for file_name in normalized_files:
                file_path = f"{self.source_dir}/{file_name}"

                try:
                    # Process only grouped-format directories (NEW STRUCTURE)
                    is_dir = self._is_directory(file_path=file_path, file_name=file_name, is_dir_hint=dir_hints.get(file_name))

                    if is_dir:
                        item_result = self._process_grouped_post(file_path, file_name)
                        if item_result['status'] == 'success':
                            result['processed_count'] += 1
                            result['processed_items'].append(item_result['data'])
                        else:
                            result['error_count'] += 1
                            result['errors'].append(item_result['error'])
                    else:
                        # Skip non-directory files (legacy single-mode structure no longer supported)
                        result['skipped_count'] += 1

                except Exception as e:
                    error_msg = f"Error processing {file_name if file_name else 'unknown file'}: {str(e)}"
                    log.warning('[RawContentProcessor]: %s', error_msg)
                    result['error_count'] += 1
                    result['errors'].append(error_msg)

            result['status'] = 'success' if result['error_count'] == 0 else 'partial'

        except Exception as e:
            error_msg = f"Failed to list source directory: {str(e)}"
            log.error('[RawContentProcessor]: %s', error_msg)
            result['status'] = 'error'
            result['errors'].append(error_msg)

        log.info(
            '[RawContentProcessor]: Processing complete - processed=%d, skipped=%d, errors=%d',
            result['processed_count'], result['skipped_count'], result['error_count']
        )
        return result

    def _process_grouped_post(
        self,
        post_dir: str,
        dir_name: str,
        content_files: list[str] | None = None,
        post_owner: str | None = None,
        post_id: str | None = None,
        source: str | None = None,
        dest_dir_override: str | None = None,
        dedupe_before_process: bool = True
    ) -> Dict[str, Any]:
        """
        Process a grouped post structure (NEW recommended format).
        Post directory contains a metadata file and all associated media.

        Processing is DB-driven: owner/post_id/source/content_files come from the scan results
        stored in the queue and are passed in here. The metadata file is NOT re-read or
        re-serialized in that case - it is simply moved to the destination as-is (preserving the
        original). The metadata file is only downloaded and parsed as a FALLBACK, when the owner
        was not supplied (e.g. process_all(), or a post whose owner scan could not resolve and
        which was not filled in manually).

        Args:
            post_dir: Full path to the post directory.
            dir_name: Name of the post directory (usually post_id).
            content_files: Content files from the scan/DB. If absent, auto-detected from the listing.
            post_owner: Owner/username from the DB row. When set, metadata is not re-read for it.
            post_id: Post id from the DB row (defaults to dir_name).
            source: Source from the DB row (defaults to 'instagram').
            dest_dir_override: Optional destination directory override for this processing call.
            dedupe_before_process: If True, remove byte-identical duplicates before moving files.

        Returns:
            Result dict with processed item data or error details.
        """
        log.info('[RawContentProcessor]: Processing grouped post directory: %s', dir_name)
        try:
            # List files in post directory with metadata (single PROPFIND) so file sizes are
            # available for the dedupe size prefilter without any extra request.
            post_files = self.webdav_client.list(post_dir, get_info=True)
            size_map = self._build_size_map(post_files)
            log.debug('[RawContentProcessor]: Found %d items in post directory %s', len(post_files), dir_name)

            # Locate the metadata file and the media files actually present in the directory.
            # NOTE: skip directory entries and the directory's own self-reference. Nextcloud's
            # PROPFIND returns the collection itself (e.g. `CmludD1NlIR/`) and webdav3 does not
            # always filter it out; treating it as a media file makes _move_grouped_files try to
            # move `<post_dir>/<post_dir>` and fail. Media = files only, never sub-dirs/self.
            metadata_file = None
            metadata_filename = None
            listed_media = []
            for entry in post_files:
                fname = self._normalize_webdav_name(entry)
                if not fname or fname == dir_name:
                    continue
                if self._raw_item_is_dir(entry):
                    continue
                if fname in ('metadata.json', 'metadata.txt'):
                    metadata_file = f"{post_dir}/{fname}"
                    metadata_filename = fname
                elif not fname.endswith(('.json', '.txt')):
                    listed_media.append(fname)

            # Resolve processing fields, preferring the DB-provided values from scan.
            resolved_owner = post_owner.strip() if (post_owner and str(post_owner).strip()) else None
            resolved_post_id = post_id or dir_name
            resolved_source = (source or 'instagram').lower()
            files = list(content_files) if content_files else (list(listed_media) or None)

            # Fallback: only read+parse the metadata file when the owner was not supplied.
            if resolved_owner is None:
                if not metadata_file:
                    error_msg = f"No metadata file found in directory {dir_name}"
                    log.error('[RawContentProcessor]: %s', error_msg)
                    return {'status': 'error', 'error': error_msg}
                log.debug('[RawContentProcessor]: Owner not provided - reading metadata from %s', metadata_file)
                metadata = self._read_metadata(self.webdav_client, metadata_file, metadata_filename)
                resolved_owner = self._resolve_owner(metadata)
                if not source:
                    resolved_source = (metadata.get('source') or 'instagram').lower()
                if not post_id:
                    resolved_post_id = metadata.get('post_id') or dir_name
                if not files:
                    meta_files = metadata.get('files') or []
                    if isinstance(meta_files, str):
                        meta_files = [meta_files]
                    files = meta_files or (list(listed_media) or None)
            else:
                log.info(
                    '[RawContentProcessor]: DB-driven processing for %s (owner=%s, post_id=%s, source=%s) - metadata not re-read',
                    dir_name, resolved_owner, resolved_post_id, resolved_source
                )

            # Validate username/owner is present (CRITICAL CHECK)
            if not resolved_owner or not str(resolved_owner).strip():
                error_msg = (
                    f"Missing required username/owner for post {dir_name}. "
                    f"Cannot process without explicit username (set it in the queue and reprocess)."
                )
                log.error('[RawContentProcessor]: %s', error_msg)
                return {'status': 'error', 'error': error_msg}
            log.info('[RawContentProcessor]: Validated username/owner for post %s: %s', dir_name, resolved_owner)

            # Sanitize the file list regardless of its source (DB row, metadata, or listing):
            # never try to move the directory's own name, path fragments, or metadata files.
            files = [
                f for f in (files or [])
                if f and str(f).strip() and str(f) != dir_name
                and '/' not in str(f) and str(f) not in ('metadata.json', 'metadata.txt')
            ]

            # Validate required fields
            if not files:
                error_msg = f"No media files found in directory {dir_name}"
                log.error('[RawContentProcessor]: %s', error_msg)
                return {'status': 'error', 'error': error_msg}

            # Optional dedupe: identifies byte-identical duplicates but does NOT delete them here —
            # they are dropped together with the whole source directory below, in one operation.
            if dedupe_before_process:
                dedupe_result = self._safe_dedupe_grouped_files(post_dir, files, size_map=size_map)
                files = dedupe_result.get('files', files)
                dup_count = len(dedupe_result.get('duplicates', []))
                if dup_count > 0:
                    log.info(
                        '[RawContentProcessor]: Dedupe: %d duplicate(s) in %s will be dropped with the source dir',
                        dup_count, dir_name
                    )
                if not files:
                    error_msg = f"No media files left after dedupe in directory {dir_name}"
                    log.error('[RawContentProcessor]: %s', error_msg)
                    return {'status': 'error', 'error': error_msg}

            # Create destination directory structure (idempotent, safe under concurrency).
            path_meta = {'username': resolved_owner, 'post_id': resolved_post_id, 'source': resolved_source}
            dest_subdir = self._create_destination_path(path_meta, resolved_source, dest_dir_override=dest_dir_override)
            log.info('[RawContentProcessor]: Creating destination directory: %s', dest_subdir)
            self._ensure_remote_dir(dest_subdir)

            # Move the kept media files to the destination.
            log.info('[RawContentProcessor]: Moving %d files from %s to %s', len(files), post_dir, dest_subdir)
            files_moved = self._move_grouped_files(post_dir, dest_subdir, files)
            log.info('[RawContentProcessor]: Successfully moved %d/%d files', files_moved, len(files))

            # Safety gate: only remove the source once ALL kept files are confirmed moved. If some
            # failed, leave the source untouched (no data loss) and report an error to retry later.
            if files_moved != len(files):
                error_msg = f"Moved {files_moved}/{len(files)} files for grouped post {dir_name}"
                log.error('[RawContentProcessor]: Processing failed - %s', error_msg)
                return {'status': 'error', 'error': error_msg}

            # All keepers are safely at the destination -> drop the ENTIRE source post directory in a
            # SINGLE operation. This removes leftover duplicates + the (now redundant) metadata file +
            # the directory itself in one request, instead of many per-file DELETEs. The critical
            # metadata already lives in the DB (owner/post_id/source/url), so the source metadata file
            # is intentionally discarded rather than archived.
            try:
                self.webdav_client.clean(post_dir)
                log.debug('[RawContentProcessor]: Removed source post directory %s', post_dir)
            except Exception as e:
                log.warning('[RawContentProcessor]: Could not remove source directory %s: %s', post_dir, str(e))

            log.info(
                '[RawContentProcessor]: Successfully processed grouped post %s (source: %s, files: %d)',
                dir_name, resolved_source, files_moved
            )
            return {
                'status': 'success',
                'data': {
                    'post_id': resolved_post_id,
                    'source': resolved_source,
                    'destination': dest_subdir,
                    'files_moved': files_moved
                }
            }

        except Exception as e:
            error_msg = f"Error processing grouped post {dir_name}: {str(e)}"
            log.error('[RawContentProcessor]: %s (type: %s)', error_msg, type(e).__name__, exc_info=True)
            return {
                'status': 'error',
                'error': error_msg
            }

    def _parse_metadata(self, content: str, filename: str) -> Dict[str, Any]:
        """
        Parse metadata from JSON or TXT format.

        Args:
            content: Raw file content.
            filename: Name of the file (used to determine format).

        Returns:
            Parsed metadata dict.

        Raises:
            ValueError: If parsing fails.
        """
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='ignore')

        if filename.endswith('.json'):
            return json.loads(content)
        elif filename.endswith('.txt'):
            # Parse TXT format: support both 'key=value' and 'Key: Value' pairs
            metadata = {}
            for line in content.strip().split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # Support both 'key=value' and 'Key: Value' formats
                if '=' in line:
                    key, value = line.split('=', 1)
                elif ':' in line:
                    key, value = line.split(':', 1)
                else:
                    continue

                key = key.strip().lower().replace(' ', '_')  # Normalize keys
                value = value.strip()

                # Handle arrays: files=[file1.jpg,file2.jpg]
                if value.startswith('[') and value.endswith(']'):
                    value = [v.strip() for v in value[1:-1].split(',') if v.strip()]

                metadata[key] = value
            return metadata
        else:
            raise ValueError(f"Unsupported metadata format: {filename}")

    @staticmethod
    def _extract_owner_from_original_filename(original_filename: Any) -> Optional[str]:
        """
        Extract owner username from legacy Original Filename field.

        Example:
            "nes.xs__2023-04-12T111111.000Z_1.jpg" -> "nes.xs"
        """
        if not original_filename:
            return None
        original_filename = str(original_filename).strip()
        if not original_filename:
            return None

        owner = original_filename.split('__', 1)[0].strip()
        return owner or None

    @staticmethod
    def _extract_owner_from_url(post_url: Any) -> Optional[str]:
        """
        Extract owner username from instagram-like URL.

        Example:
            https://www.instagram.com/nes.xs/p/Cq7... -> nes.xs
        """
        if not post_url:
            return None
        post_url = str(post_url).strip()
        if not post_url:
            return None

        match = re.search(r"instagram\.com/([^/]+)/p/", post_url)
        if match:
            return match.group(1).strip() or None
        return None

    def _resolve_owner(self, metadata: Dict[str, Any]) -> Optional[str]:
        """
        Resolve owner with fallback order:
        post_owner -> owner -> username -> author -> original_filename prefix -> URL path.
        """
        direct_owner = (
            metadata.get('post_owner')
            or metadata.get('owner')
            or metadata.get('username')
            or metadata.get('author')
        )
        if isinstance(direct_owner, str) and direct_owner.strip():
            return direct_owner.strip()

        from_original = self._extract_owner_from_original_filename(
            metadata.get('original_filename')
        )
        if from_original:
            return from_original

        from_url = self._extract_owner_from_url(
            metadata.get('post_url') or metadata.get('url') or metadata.get('link') or metadata.get('post_link')
        )
        if from_url:
            return from_url

        return None

    def _create_destination_path(
        self,
        metadata: Dict[str, Any],
        source: str,
        dest_dir_override: str | None = None
    ) -> str:
        """
        Create structured destination path based on metadata.
        Uses the same structure as uploader for direct links: {dest_dir}/{source}/{username}

        Args:
            metadata: Post metadata dict.
            source: Content source (e.g., 'instagram').
            dest_dir_override: Optional destination directory override.

        Returns:
            Full destination path.
        """
        username = metadata.get('username')
        if not (isinstance(username, str) and username.strip()):
            username = self._resolve_owner(metadata)

        if not (isinstance(username, str) and username.strip()):
            username = 'unknown'

        username = username.strip().strip('/')

        base_dest = str(dest_dir_override or self.dest_dir or '').strip().rstrip('/')
        normalized_source = str(source or '').strip().strip('/').lower()

        # Avoid duplicated provider in path when dest_dir already includes it,
        # e.g. dest_dir=data/instagram and source=instagram.
        last_segment = base_dest.split('/')[-1].lower() if base_dest else ''
        if normalized_source and last_segment == normalized_source:
            dest_path = f"{base_dest}/{username}"
        else:
            dest_path = f"{base_dest}/{normalized_source}/{username}" if normalized_source else f"{base_dest}/{username}"

        return dest_path

    def _move_grouped_files(self, source_post_dir: str, dest_dir: str, files_list: list) -> int:
        """
        Move media files from grouped post directory to destination.

        Args:
            source_post_dir: Source post directory path.
            dest_dir: Destination directory.
            files_list: List of filenames to move.

        Returns:
            Number of files moved.
        """
        files_moved = 0
        failed_files = []

        for file_name in files_list:
            try:
                source_path = f"{source_post_dir}/{file_name}"
                dest_path = f"{dest_dir}/{file_name}"

                log.debug('[RawContentProcessor]: Moving file: %s', file_name)
                # WebDAV3: server-side MOVE (rename on the same storage) - no bytes cross the
                # wire, unlike the previous download_from -> upload_to -> clean round trip.
                self._with_retry(
                    lambda s=source_path, d=dest_path: self.webdav_client.move(
                        remote_path_from=s, remote_path_to=d, overwrite=True
                    ),
                    f"move {file_name}"
                )

                files_moved += 1
                log.debug('[RawContentProcessor]: Successfully moved %s', file_name)

            except Exception as e:
                failed_files.append((file_name, str(e)))
                log.error('[RawContentProcessor]: Failed to move file %s: %s', file_name, str(e))

        if failed_files:
            log.warning('[RawContentProcessor]: Failed to move %d/%d files', len(failed_files), len(files_list))

        return files_moved

    @staticmethod
    def _build_size_map(entries: Any) -> Dict[str, Optional[int]]:
        """
        Build a basename -> byte size map from a list(get_info=True) result.

        Sizes come for free with the directory listing (a single PROPFIND) and drive the dedupe
        size prefilter. Entries without a parseable size map to None so they fall back to hashing.
        """
        sizes: Dict[str, Optional[int]] = {}
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            name = RawContentProcessor._normalize_webdav_name(entry)
            if not name:
                continue
            raw_size = entry.get('size')
            try:
                sizes[name] = int(raw_size) if raw_size is not None else None
            except (TypeError, ValueError):
                sizes[name] = None
        return sizes

    def _hash_remote_file(self, remote_path: str, limit: Optional[int] = None, client: Optional[Any] = None) -> str:
        """
        Compute the sha256 of a remote file in a SINGLE request, without buffering it in memory.

        Unlike webdav3's download_iter/download_from (which each fire is_dir() + check() + GET = 3
        round trips), this issues one GET straight through execute_request. When `limit` is set it
        sends a Range header so only the first `limit` bytes are transferred.

        Args:
            remote_path: Full WebDAV path to the file.
            limit: When set, hash only the first `limit` bytes (ranged fingerprint). None = full file.
            client: WebDAV client to use (defaults to self.webdav_client); pass a per-thread client
                when hashing concurrently.

        Returns:
            Hex sha256 digest of the (possibly truncated) content.
        """
        client = client or self.webdav_client
        urn = Urn(remote_path)
        headers_ext = [f"Range: bytes=0-{limit - 1}"] if limit else None
        response = client.execute_request(action="download", path=urn.quote(), headers_ext=headers_ext)
        hasher = hashlib.sha256()
        read = 0
        for chunk in response.iter_content(chunk_size=DEDUPE_HEAD_BYTES):
            if not chunk:
                continue
            if limit is not None and read + len(chunk) >= limit:
                hasher.update(chunk[:limit - read])
                break
            hasher.update(chunk)
            read += len(chunk)
        return hasher.hexdigest()

    def _safe_dedupe_grouped_files(
        self,
        source_post_dir: str,
        files_list: list[str],
        size_map: Optional[Dict[str, Optional[int]]] = None
    ) -> Dict[str, Any]:
        """
        Identify byte-identical duplicates and return the files to KEEP (one per content).

        Duplicates are NOT deleted here — the caller removes the whole source directory in a single
        operation after moving the keepers, so the dups die with it (no per-file DELETE churn / trash).

        Cost model (as few requests as possible):
        - group by byte size from size_map (no I/O). A unique size cannot have a byte-identical twin,
          so those files are kept with zero downloads.
        - only same-size files are hashed, one GET each (Range-limited for large files), in parallel.

        Rules:
        - Never remove the only copy of content (keep the first file per content, in original order).
        - Only files with an identical size AND hash are treated as duplicates.
        - If a file can't be hashed, keep it (never drop on uncertainty).

        Note: unknown-size files share one bucket (compared only against each other), never grouped
        with a known-size file; worst case a missed dedupe, never a wrong deletion.

        Returns:
            {'files': [keepers in original order], 'duplicates': [names to drop with the source dir]}
        """
        size_map = size_map or {}

        unique_files = []
        seen_filenames = set()
        for fname in files_list or []:
            clean_name = str(fname).strip()
            if not clean_name or clean_name in seen_filenames:
                continue
            seen_filenames.add(clean_name)
            unique_files.append(clean_name)

        order = {name: idx for idx, name in enumerate(unique_files)}
        keepers: list[str] = []
        duplicates: list[str] = []

        # Group by size (no download). Unknown sizes share one bucket.
        by_size: Dict[Any, list[str]] = {}
        for file_name in unique_files:
            size = size_map.get(file_name)
            key = size if size is not None else '__unknown_size__'
            by_size.setdefault(key, []).append(file_name)

        # Only same-size files need hashing; unique-size files are kept as-is.
        to_hash: list[tuple] = []
        for size_key, group in by_size.items():
            if len(group) == 1:
                keepers.append(group[0])
            else:
                to_hash.extend((name, size_key) for name in group)

        # Per-thread WebDAV client for concurrent hashing (webdav3 client is not thread-safe).
        thread_local = threading.local()

        def _client():
            if not self.client_factory:
                return self.webdav_client
            client = getattr(thread_local, 'client', None)
            if client is None:
                client = self.client_factory()
                thread_local.client = client
            return client

        def _hash_one(item: tuple) -> tuple:
            name, size_key = item
            size_value = size_key if isinstance(size_key, int) else None
            # Small files: one full-hash request. Large files: a cheap Range fingerprint.
            limit = None if (size_value is None or size_value <= DEDUPE_FULL_HASH_MAX_BYTES) else DEDUPE_HEAD_BYTES
            try:
                digest = self._hash_remote_file(f"{source_post_dir}/{name}", limit=limit, client=_client())
                return name, digest
            except Exception as e:  # pylint: disable=broad-exception-caught
                log.warning(
                    '[RawContentProcessor]: Could not hash %s during dedupe (%s). Keeping file for safety.',
                    name, str(e)
                )
                return name, None

        hashes: Dict[str, Optional[str]] = {}
        if to_hash:
            if self.client_factory and len(to_hash) > 1:
                workers = min(DEDUPE_HASH_WORKERS, len(to_hash))
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    for name, digest in executor.map(_hash_one, to_hash):
                        hashes[name] = digest
            else:
                for item in to_hash:
                    name, digest = _hash_one(item)
                    hashes[name] = digest

        # Keep the first file per (size, hash); the rest are duplicates. Process in original order
        # so the retained copy is deterministic.
        seen_key: Dict[tuple, str] = {}
        for name, size_key in sorted(to_hash, key=lambda t: order.get(t[0], len(order))):
            digest = hashes.get(name)
            if digest is None:
                keepers.append(name)
                continue
            key = (size_key, digest)
            if key not in seen_key:
                seen_key[key] = name
                keepers.append(name)
            else:
                duplicates.append(name)
                log.info(
                    '[RawContentProcessor]: Duplicate in %s: %s == %s (same size+content) - will drop with source dir',
                    source_post_dir, name, seen_key[key]
                )

        keepers.sort(key=lambda n: order.get(n, len(order)))
        return {'files': keepers, 'duplicates': duplicates}

    def _move_associated_files(
        self,
        metadata: Dict[str, Any],
        dest_dir: str,
        source: str,
        source_dir: str | None = None
    ) -> int:
        """
        Move media files associated with the post to the destination (DEPRECATED - for old structure).

        Args:
            metadata: Post metadata containing file references.
            dest_dir: Destination directory.
            source: Content source.
            source_dir: Optional source directory override.

        Returns:
            Number of files moved.
        """
        files_moved = 0
        files_to_move = metadata.get('files', [])
        base_source_dir = source_dir or self.source_dir

        for file_name in files_to_move:
            try:
                source_path = f"{base_source_dir}/{file_name}"
                dest_path = f"{dest_dir}/{file_name}"

                # WebDAV3: server-side MOVE (no byte transfer through the app).
                self._with_retry(
                    lambda s=source_path, d=dest_path: self.webdav_client.move(
                        remote_path_from=s, remote_path_to=d, overwrite=True
                    ),
                    f"move {file_name}"
                )

                files_moved += 1
                log.info('[RawContentProcessor]: Moved %s to %s', file_name, dest_path)

            except Exception as e:
                log.warning('[RawContentProcessor]: Could not move file %s: %s', file_name, str(e))

        return files_moved

    def _save_metadata(self, dest_dir: str, organized_data: Dict[str, Any]) -> None:
        """
        Save organized metadata to destination.

        Args:
            dest_dir: Destination directory.
            organized_data: Organized metadata dict.
        """
        try:
            metadata_path = f"{dest_dir}/metadata.json"
            metadata_json = json.dumps(organized_data, indent=2, default=str)
            # WebDAV3 Client: use upload_to with BytesIO
            self.webdav_client.upload_to(buff=io.BytesIO(metadata_json.encode('utf-8')), remote_path=metadata_path)
            log.debug('[RawContentProcessor]: Saved metadata to %s', metadata_path)
        except Exception as e:
            log.warning('[RawContentProcessor]: Could not save metadata: %s', str(e))


class InstagramAdapter(ContentProcessor):
    """
    Adapter for processing content from Instagram.
    Extends ContentProcessor for Instagram-specific logic.
    """

    def fetch_content(self) -> Any:
        """Fetch content from Instagram."""
        raise NotImplementedError("Use Downloader module for Instagram content")

    def organize_content(self, raw_data: Any) -> Dict[str, Any]:
        """Organize Instagram content into structured format."""
        raise NotImplementedError("Implement in subclass")

    def save_content(self, structured_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save organized Instagram content."""
        raise NotImplementedError("Implement in subclass")


class InstagramRawAdapter:
    """
    Adapter for processing raw Instagram content from browser extensions.
    Handles metadata parsing and file organization.
    """

    def __init__(self, metadata: Dict[str, Any], webdav_client: object):
        """
        Initialize the Instagram raw adapter.

        Args:
            metadata: Post metadata from raw content.
            webdav_client: WebDAV client for file operations.
        """
        self.metadata = metadata
        self.webdav_client = webdav_client

    def organize(self) -> Dict[str, Any]:
        """
        Organize raw Instagram metadata into structured format.

        Returns:
            Organized metadata dict ready for storage.
        """
        return {
            'post_id': self.metadata.get('post_id'),
            'source': 'instagram',
            'username': self.metadata.get('username'),
            'caption': self.metadata.get('caption'),
            'created_at': self.metadata.get('created_at'),
            'media_count': len(self.metadata.get('files', [])),
            'raw_metadata': self.metadata
        }
