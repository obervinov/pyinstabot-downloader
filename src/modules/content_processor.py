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
import hashlib
from typing import Dict, Optional, Any
from logger import log


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
        """
        self.webdav_client = webdav_client
        self.source_dir = source_dir
        self.dest_dir = dest_dir
        self.database = database
        self.adapter_map = kwargs.get('adapter_map', {'instagram': InstagramRawAdapter})
        log.info('[RawContentProcessor]: Initialized with source=%s, dest=%s', source_dir, dest_dir)

    @staticmethod
    def _normalize_webdav_name(item: Any) -> str:
        """
        Normalize WebDAV list item to plain filename.

        Supports both list formats:
        - 'filename.ext'
        - {'name': 'filename.ext'}
        - '/path/to/filename.ext/'
        """
        if isinstance(item, dict):
            raw_name = str(item.get('name', ''))
        else:
            raw_name = str(item)

        # Strip trailing slash and keep basename only
        result = raw_name.rstrip('/').split('/')[-1]
        if not result:
            log.debug('[RawContentProcessor]: _normalize returned empty string from: %s', str(item))
        return result

    def _is_directory(self, file_path: str, file_name: str) -> bool:
        """
        Best-effort check if WebDAV path points to a directory.
        Uses multiple strategies: extension-based filtering, info() metadata, and listing.
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

        # Try info() call first
        try:
            info = self.webdav_client.info(file_path)
            if isinstance(info, dict):
                content_type = str(info.get('content_type', '')).lower()
                if 'directory' in content_type:
                    log.debug('[RawContentProcessor]: info() returned directory content-type for %s', file_name)
                    return True
                if 'application/json' in content_type or 'text/plain' in content_type:
                    log.debug('[RawContentProcessor]: info() returned file content-type for %s', file_name)
                    return False
                if info.get('isdir') is True:
                    log.debug('[RawContentProcessor]: info() returned isdir=True for %s', file_name)
                    return True
                if info.get('isdir') is False:
                    log.debug('[RawContentProcessor]: info() returned isdir=False for %s', file_name)
                    return False
        except Exception as info_error:
            log.debug('[RawContentProcessor]: info() failed for %s: %s', file_name, str(info_error))

        # Fallback: try listing path (if we can list it, it's a directory)
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

            normalized_items = [self._normalize_webdav_name(item) for item in raw_items]
            normalized_items = [item for item in normalized_items if item]
            result['total_items'] = len(normalized_items)
            log.debug('[RawContentProcessor]: After normalization: %d valid items', result['total_items'])

            # NOTE: We scan ALL items first to get processable candidates,
            # then apply offset/limit AFTER filtering to ensure consistent pagination.
            result['scanned_items'] = len(normalized_items)

            new_items_found = 0
            source_items_set = set(normalized_items)

            for idx, file_name in enumerate(normalized_items, 1):
                file_path = f"{source_dir}/{file_name}"

                # Skip if already completed
                if file_path in completed_paths:
                    log.debug('[RawContentProcessor]: [%d/%d] Skipping completed: %s', idx, result['scanned_items'], file_name)
                    result['skipped_count'] += 1
                    continue

                # NEW STRUCTURE: grouped post directory
                is_dir = self._is_directory(file_path=file_path, file_name=file_name)

                if is_dir:
                    log.info('[RawContentProcessor]: [%d/%d] Found grouped-mode item (directory): %s', idx, result['scanned_items'], file_name)

                    # Try to list files in directory for grouped mode
                    content_files = []
                    post_id = file_name
                    post_url = None
                    post_owner = None
                    source = 'instagram'
                    metadata_file = None
                    nested_added = 0
                    try:
                        items_in_dir = self.webdav_client.list(file_path)
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

                        # Container directory support (e.g. __extenstion-ff/<post-id>)
                        # If metadata file is absent in current dir, try nested directories as real grouped posts.
                        if items_in_dir and not metadata_file:
                            for item in items_in_dir:
                                nested_name = self._normalize_webdav_name(item)
                                if not nested_name:
                                    continue

                                nested_path = f"{file_path}/{nested_name}"
                                if not self._is_directory(file_path=nested_path, file_name=nested_name):
                                    continue

                                nested_files = self.webdav_client.list(nested_path)
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

                                nested_post_id = nested_name
                                nested_post_url = None
                                nested_post_owner = None
                                nested_source = 'instagram'

                                metadata_buffer = io.BytesIO()
                                self.webdav_client.download_from(
                                    buff=metadata_buffer,
                                    remote_path=f"{nested_path}/{nested_metadata_file}"
                                )
                                metadata_content = metadata_buffer.getvalue().decode('utf-8', errors='ignore')
                                metadata = self._parse_metadata(metadata_content, nested_metadata_file)

                                nested_post_id = metadata.get('post_id') or nested_name
                                nested_post_url = (
                                    metadata.get('post_url')
                                    or metadata.get('url')
                                    or metadata.get('link')
                                    or metadata.get('post_link')
                                )
                                nested_post_owner = self._resolve_owner(metadata)
                                nested_source = (metadata.get('source') or 'instagram').lower()

                                # Check if username/owner is missing
                                requires_username = not nested_post_owner or not str(nested_post_owner).strip()
                                if requires_username:
                                    log.warning(
                                        '[RawContentProcessor]: [nested %s] MISSING USERNAME/OWNER - post will require explicit username before processing. '
                                        'Metadata keys checked: username=%s, post_owner=%s, owner=%s',
                                        nested_name,
                                        metadata.get('username'),
                                        metadata.get('post_owner'),
                                        metadata.get('owner')
                                    )

                                parsed_files = metadata.get('files') or []
                                if isinstance(parsed_files, str):
                                    parsed_files = [parsed_files]

                                # Check for mismatch between metadata and actual files in directory
                                if parsed_files:
                                    parsed_set = {f for f in parsed_files if f}
                                    if parsed_set:
                                        # Verify that metadata files match actual files
                                        if len(parsed_set) != len(nested_content_files):
                                            log.warning(
                                                '[RawContentProcessor]: [nested %s] File count mismatch: metadata has %d files, directory has %d files. '
                                                'Using actual directory files. Metadata: %s | Directory: %s',
                                                nested_name, len(parsed_set), len(nested_content_files), list(parsed_set), nested_content_files
                                            )
                                            # Use actual directory files, ignore metadata list
                                        else:
                                            # Count matches, try to filter by metadata list
                                            filtered_files = [f for f in nested_content_files if f in parsed_set]
                                            if len(filtered_files) == len(nested_content_files):
                                                # All files from directory are in metadata - good!
                                                log.debug(
                                                    '[RawContentProcessor]: [nested %s] File count verified: %d files match metadata',
                                                    nested_name, len(filtered_files)
                                                )
                                                nested_content_files = filtered_files
                                            else:
                                                # Some files in directory don't match metadata names
                                                log.warning(
                                                    '[RawContentProcessor]: [nested %s] File name mismatch: metadata names don\'t match directory. '
                                                    'Using actual directory files. Metadata: %s | Directory: %s',
                                                    nested_name, list(parsed_set), nested_content_files
                                                )
                                                # Use actual directory files

                                result['processable_items'].append({
                                    'item_name': nested_name,
                                    'item_path': nested_path,
                                    'mode': 'grouped',
                                    'post_id': nested_post_id,
                                    'post_url': nested_post_url,
                                    'post_owner': nested_post_owner,
                                    'source': nested_source,
                                    'content_files_json': json.dumps(nested_content_files),
                                    'requires_username': requires_username
                                })
                                new_items_found += 1
                                nested_added += 1

                            if nested_added > 0:
                                log.info(
                                    '[RawContentProcessor]: [%d/%d] Container directory %s expanded into %d grouped candidates',
                                    idx, result['scanned_items'], file_name, nested_added
                                )
                                continue

                        if metadata_file:
                            metadata_buffer = io.BytesIO()
                            self.webdav_client.download_from(
                                buff=metadata_buffer,
                                remote_path=f"{file_path}/{metadata_file}"
                            )
                            metadata_content = metadata_buffer.getvalue().decode('utf-8', errors='ignore')
                            metadata = self._parse_metadata(metadata_content, metadata_file)

                            post_id = metadata.get('post_id') or file_name
                            post_url = (
                                metadata.get('post_url')
                                or metadata.get('url')
                                or metadata.get('link')
                                or metadata.get('post_link')
                            )
                            post_owner = self._resolve_owner(metadata)
                            source = (metadata.get('source') or 'instagram').lower()

                            # Check if username/owner is missing
                            requires_username = not post_owner or not str(post_owner).strip()
                            if requires_username:
                                log.warning(
                                    '[RawContentProcessor]: [%s] MISSING USERNAME/OWNER - post will require explicit username before processing. '
                                    'Metadata keys checked: username=%s, post_owner=%s, owner=%s',
                                    file_name,
                                    metadata.get('username'),
                                    metadata.get('post_owner'),
                                    metadata.get('owner')
                                )

                            parsed_files = metadata.get('files') or []
                            if isinstance(parsed_files, str):
                                parsed_files = [parsed_files]

                            # Check for mismatch between metadata and actual files in directory
                            if parsed_files:
                                parsed_set = {f for f in parsed_files if f}
                                if parsed_set:
                                    # Verify that metadata files match actual files
                                    if len(parsed_set) != len(content_files):
                                        log.warning(
                                            '[RawContentProcessor]: [%s] File count mismatch: metadata has %d files, directory has %d files. '
                                            'Using actual directory files. Metadata: %s | Directory: %s',
                                            file_name, len(parsed_set), len(content_files), list(parsed_set), content_files
                                        )
                                        # Use actual directory files, ignore metadata list
                                    else:
                                        # Count matches, try to filter by metadata list
                                        filtered_files = [f for f in content_files if f in parsed_set]
                                        if len(filtered_files) == len(content_files):
                                            # All files from directory are in metadata - good!
                                            log.debug(
                                                '[RawContentProcessor]: [%s] File count verified: %d files match metadata',
                                                file_name, len(filtered_files)
                                            )
                                            content_files = filtered_files
                                        else:
                                            # Some files in directory don't match metadata names
                                            log.warning(
                                                '[RawContentProcessor]: [%s] File name mismatch: metadata names don\'t match directory. '
                                                'Using actual directory files. Metadata: %s | Directory: %s',
                                                file_name, list(parsed_set), content_files
                                            )
                                            # Use actual directory files
                    except Exception:
                        pass

                    # Skip container/empty directories from queue if they do not represent
                    # a direct grouped post (no metadata at this level) and did not expand.
                    if not metadata_file:
                        log.debug(
                            '[RawContentProcessor]: [%d/%d] Skipping top-level/container directory without metadata: %s',
                            idx,
                            result['scanned_items'],
                            file_name
                        )
                        result['skipped_count'] += 1
                        continue

                    result['processable_items'].append({
                        'item_name': file_name,
                        'item_path': file_path,
                        'mode': 'grouped',
                        'post_id': post_id,
                        'post_url': post_url,
                        'post_owner': post_owner,
                        'source': source,
                        'content_files_json': json.dumps(content_files),
                        'requires_username': requires_username
                    })
                    new_items_found += 1
                    continue

                log.debug('[RawContentProcessor]: [%d/%d] Skipping non-processable: %s', idx, result['scanned_items'], file_name)
                result['skipped_count'] += 1

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
            dest_dir_override=dest_dir_override,
            dedupe_before_process=dedupe_before_process
        )

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
            normalized_files = [self._normalize_webdav_name(item) for item in files]
            normalized_files = [item for item in normalized_files if item]
            log.info('[RawContentProcessor]: Found %d items in source directory', len(normalized_files))

            for file_name in normalized_files:
                file_path = f"{self.source_dir}/{file_name}"

                try:
                    # Process only grouped-format directories (NEW STRUCTURE)
                    is_dir = self._is_directory(file_path=file_path, file_name=file_name)

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
        dest_dir_override: str | None = None,
        dedupe_before_process: bool = True
    ) -> Dict[str, Any]:
        """
        Process a grouped post structure (NEW recommended format).
        Post directory contains metadata file and all associated media.

        Args:
            post_dir: Full path to the post directory.
            dir_name: Name of the post directory (usually post_id).
            content_files: List of content files from database scan (optional).
                If provided, uses these files instead of auto-detecting from metadata.
            dest_dir_override: Optional destination directory override for this processing call.
            dedupe_before_process: If True, remove byte-identical duplicates before moving files.

        Returns:
            Result dict with processed item data or error details.
        """
        log.info('[RawContentProcessor]: Processing grouped post directory: %s', dir_name)
        try:
            # List files in post directory
            post_files = self.webdav_client.list(post_dir)
            log.debug('[RawContentProcessor]: Found %d items in post directory %s', len(post_files), dir_name)

            # Find metadata file
            metadata_file = None
            metadata_filename = None
            for file_name in post_files:
                fname = self._normalize_webdav_name(file_name)
                if fname in ('metadata.json', 'metadata.txt'):
                    metadata_file = f"{post_dir}/{fname}"
                    metadata_filename = fname
                    log.debug('[RawContentProcessor]: Found metadata file: %s', fname)
                    break

            if not metadata_file:
                error_msg = f"No metadata file found in directory {dir_name}"
                log.error('[RawContentProcessor]: %s', error_msg)
                return {
                    'status': 'error',
                    'error': error_msg
                }

            # Read and parse metadata
            log.debug('[RawContentProcessor]: Reading metadata from %s', metadata_file)
            # WebDAV3 Client: read file content using BytesIO buffer
            buffer = io.BytesIO()
            self.webdav_client.download_from(buff=buffer, remote_path=metadata_file)
            metadata_content = buffer.getvalue().decode('utf-8')
            metadata = self._parse_metadata(metadata_content, metadata_filename)
            log.debug(
                '[RawContentProcessor]: Parsed metadata: post_id=%s, source=%s, files=%d',
                metadata.get('post_id'), metadata.get('source'), len(metadata.get('files', []))
            )

            # Use content_files from database if provided (from scan_source result)
            if content_files:
                log.info(
                    '[RawContentProcessor]: Using %d content files from database for %s',
                    len(content_files), dir_name
                )
                metadata['files'] = content_files
            # Otherwise, auto-populate files array if not present
            elif not metadata.get('files'):
                media_files = []
                for file_name in post_files:
                    fname = self._normalize_webdav_name(file_name)
                    if fname not in ('metadata.json', 'metadata.txt'):
                        media_files.append(fname)
                metadata['files'] = media_files
                log.info(
                    '[RawContentProcessor]: Auto-detected %d media files in %s: %s',
                    len(media_files), dir_name, ', '.join(media_files[:5]) + ('...' if len(media_files) > 5 else '')
                )

            # Add default source if not specified
            if not metadata.get('source'):
                metadata['source'] = 'instagram'
                log.debug('[RawContentProcessor]: Using default source: instagram')

            # Use directory name as post_id if not in metadata
            if not metadata.get('post_id'):
                metadata['post_id'] = dir_name
                log.debug('[RawContentProcessor]: Using directory name as post_id: %s', dir_name)

            # Validate username/owner is present (CRITICAL CHECK)
            post_owner = self._resolve_owner(metadata)
            if not post_owner or not str(post_owner).strip():
                error_msg = (
                    f"Missing required username/owner for post {dir_name}. "
                    f"Cannot process without explicit username. "
                    f"Metadata keys checked: username={metadata.get('username')}, "
                    f"post_owner={metadata.get('post_owner')}, owner={metadata.get('owner')}"
                )
                log.error('[RawContentProcessor]: %s', error_msg)
                return {
                    'status': 'error',
                    'error': error_msg
                }

            log.info('[RawContentProcessor]: Validated username/owner for post %s: %s', dir_name, post_owner)

            # Validate required fields
            if not metadata.get('files'):
                error_msg = f"No media files found in directory {dir_name}"
                log.error('[RawContentProcessor]: %s', error_msg)
                return {
                    'status': 'error',
                    'error': error_msg
                }

            # Optional safe dedupe before processing (byte-identical files only)
            if dedupe_before_process:
                dedupe_result = self._safe_dedupe_grouped_files(post_dir, metadata.get('files', []))
                metadata['files'] = dedupe_result.get('files', metadata.get('files', []))
                removed_count = len(dedupe_result.get('removed', []))
                failed_cleanup_count = len(dedupe_result.get('failed_cleanup', []))
                if removed_count > 0:
                    log.info(
                        '[RawContentProcessor]: Dedupe removed %d duplicate files in %s before processing',
                        removed_count,
                        dir_name
                    )
                if failed_cleanup_count > 0:
                    log.warning(
                        '[RawContentProcessor]: Dedupe found %d duplicates but failed to cleanup them in %s. '
                        'They will be moved to avoid data loss.',
                        failed_cleanup_count,
                        dir_name
                    )

                if not metadata.get('files'):
                    error_msg = f"No media files left after dedupe in directory {dir_name}"
                    log.error('[RawContentProcessor]: %s', error_msg)
                    return {
                        'status': 'error',
                        'error': error_msg
                    }

            # Determine source adapter
            source = metadata.get('source', 'instagram').lower()
            adapter_class = self.adapter_map.get(source, InstagramRawAdapter)
            adapter = adapter_class(metadata=metadata, webdav_client=self.webdav_client)
            log.debug('[RawContentProcessor]: Using adapter for source: %s', source)

            # Organize content using adapter
            organized_data = adapter.organize()

            # Create destination directory structure
            dest_subdir = self._create_destination_path(metadata, source, dest_dir_override=dest_dir_override)
            log.info('[RawContentProcessor]: Creating destination directory: %s', dest_subdir)
            self.webdav_client.mkdir(dest_subdir)

            # Move files from post directory to destination
            log.info(
                '[RawContentProcessor]: Moving %d files from %s to %s',
                len(metadata['files']), post_dir, dest_subdir
            )
            files_moved = self._move_grouped_files(post_dir, dest_subdir, metadata['files'])
            log.info('[RawContentProcessor]: Successfully moved %d/%d files', files_moved, len(metadata['files']))

            # Cleanup source directory after file moves
            # Check what's left in the source directory
            remaining_items = []
            try:
                items_in_dir = self.webdav_client.list(post_dir)
                if items_in_dir:
                    for item in items_in_dir:
                        # Check if item is a directory (ends with /) before normalizing
                        raw_item = str(item.get('name', '') if isinstance(item, dict) else item)
                        is_directory = raw_item.rstrip('/') != raw_item  # True if has trailing slash

                        fname = self._normalize_webdav_name(item)
                        # Only flag non-metadata FILES (not directories)
                        if fname and not is_directory and fname not in ('metadata.json', 'metadata.txt'):
                            remaining_items.append(fname)
            except Exception as e:
                log.warning('[RawContentProcessor]: Could not list source directory to check remaining items: %s', str(e))

            expected_files = len(metadata['files'])

            # Check if processing was truly successful
            if files_moved != expected_files:
                # Not all files were moved - this is an error
                error_msg = f"Moved {files_moved}/{expected_files} files for grouped post {dir_name}"
                log.error('[RawContentProcessor]: Processing failed - %s', error_msg)
                return {
                    'status': 'error',
                    'error': error_msg
                }

            # All files were moved, now check cleanup
            if remaining_items:
                # Files are remaining in source directory (other than metadata)
                error_msg = (
                    f"Source directory {post_dir} still contains non-metadata files after processing: "
                    f"{', '.join(remaining_items)}. Directory will NOT be deleted. "
                    f"Please check and clean up manually or reprocess."
                )
                log.error('[RawContentProcessor]: %s', error_msg)
                return {
                    'status': 'error',
                    'error': error_msg
                }

            # All files moved and no extra files left - safe to cleanup
            # Delete metadata file from source
            try:
                log.debug('[RawContentProcessor]: All files moved successfully, deleting source metadata file: %s', metadata_file)
                self.webdav_client.clean(metadata_file)
            except Exception as e:
                log.warning('[RawContentProcessor]: Failed to delete metadata file %s: %s', metadata_file, str(e))

            # Try to delete the empty source directory
            try:
                log.debug('[RawContentProcessor]: Attempting to delete empty source directory: %s', post_dir)
                self.webdav_client.clean(post_dir)
                log.debug('[RawContentProcessor]: Successfully deleted empty source directory')
            except Exception as e:
                log.debug('[RawContentProcessor]: Could not delete source directory %s (may not be empty): %s', post_dir, str(e))

            # Save organized metadata
            self._save_metadata(dest_subdir, organized_data)

            log.info(
                '[RawContentProcessor]: Successfully processed grouped post %s (source: %s, files: %d)',
                dir_name, source, files_moved
            )
            return {
                'status': 'success',
                'data': {
                    'post_id': metadata.get('post_id'),
                    'source': source,
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
                # WebDAV3: use download_from/upload_to with BytesIO
                content_buffer = io.BytesIO()
                self.webdav_client.download_from(buff=content_buffer, remote_path=source_path)
                content_bytes = content_buffer.getvalue()

                # Upload to destination
                self.webdav_client.upload_to(buff=io.BytesIO(content_bytes), remote_path=dest_path)
                # Delete from source
                self.webdav_client.clean(source_path)

                files_moved += 1
                log.debug('[RawContentProcessor]: Successfully moved %s (%d bytes)', file_name, len(content_bytes))

            except Exception as e:
                failed_files.append((file_name, str(e)))
                log.error('[RawContentProcessor]: Failed to move file %s: %s', file_name, str(e))

        if failed_files:
            log.warning('[RawContentProcessor]: Failed to move %d/%d files', len(failed_files), len(files_list))

        return files_moved

    def _safe_dedupe_grouped_files(self, source_post_dir: str, files_list: list[str]) -> Dict[str, Any]:
        """
        Safely dedupe grouped post files by byte-identical content.

        Rules:
        - Never remove the only copy of content (always keep first file per hash).
        - Remove only exact byte-identical duplicates.
        - If duplicate cleanup fails, keep file for moving (avoid data loss).
        """
        unique_files = []
        seen_filenames = set()
        for fname in files_list or []:
            clean_name = str(fname).strip()
            if not clean_name or clean_name in seen_filenames:
                continue
            seen_filenames.add(clean_name)
            unique_files.append(clean_name)

        hash_to_keeper: dict[str, str] = {}
        duplicates_to_remove: list[str] = []
        files_to_move: list[str] = []
        failed_cleanup: list[str] = []

        for file_name in unique_files:
            source_path = f"{source_post_dir}/{file_name}"
            try:
                content_buffer = io.BytesIO()
                self.webdav_client.download_from(buff=content_buffer, remote_path=source_path)
                content_bytes = content_buffer.getvalue()
                content_hash = hashlib.sha256(content_bytes).hexdigest()

                if content_hash not in hash_to_keeper:
                    hash_to_keeper[content_hash] = file_name
                    files_to_move.append(file_name)
                else:
                    keeper = hash_to_keeper[content_hash]
                    duplicates_to_remove.append(file_name)
                    log.info(
                        '[RawContentProcessor]: Duplicate detected in %s: %s == %s (same content hash)',
                        source_post_dir,
                        file_name,
                        keeper
                    )
            except Exception as e:
                log.warning(
                    '[RawContentProcessor]: Could not hash file %s during dedupe (%s). Keeping file for safety.',
                    source_path,
                    str(e)
                )
                files_to_move.append(file_name)

        removed: list[str] = []
        for dup_name in duplicates_to_remove:
            dup_path = f"{source_post_dir}/{dup_name}"
            try:
                self.webdav_client.clean(dup_path)
                removed.append(dup_name)
            except Exception as e:
                failed_cleanup.append(dup_name)
                files_to_move.append(dup_name)
                log.warning(
                    '[RawContentProcessor]: Failed to cleanup duplicate %s (%s). Will move file instead.',
                    dup_path,
                    str(e)
                )

        return {
            'files': files_to_move,
            'removed': removed,
            'failed_cleanup': failed_cleanup
        }

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

                # WebDAV3: use download_from/upload_to with BytesIO
                content_buffer = io.BytesIO()
                self.webdav_client.download_from(buff=content_buffer, remote_path=source_path)
                content_bytes = content_buffer.getvalue()

                # Upload to destination
                self.webdav_client.upload_to(buff=io.BytesIO(content_bytes), remote_path=dest_path)
                # Delete from source
                self.webdav_client.clean(source_path)

                files_moved += 1
                log.info('[RawContentProcessor]: Moved %s to %s (%d bytes)', file_name, dest_path, len(content_bytes))

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
