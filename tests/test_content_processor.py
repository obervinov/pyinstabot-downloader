"""
Tests for the content processing module.

Tests cover:
- RawContentProcessor initialization and configuration
- Raw content processing from WebDAV
- Adapter pattern for different sources (Instagram)
- File organization and metadata handling
"""

import json
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime

from src.modules.content_processor import (
    ContentProcessor,
    RawContentProcessor,
    InstagramAdapter,
    InstagramRawAdapter
)


class TestContentProcessor:
    """Tests for base ContentProcessor class."""

    def test_content_processor_init(self):
        """Test ContentProcessor initialization."""
        config = {'api_key': 'test_key', 'endpoint': 'https://api.example.com'}
        processor = ContentProcessor(config)
        assert processor.source_config == config

    def test_fetch_content_not_implemented(self):
        """Test that fetch_content raises NotImplementedError."""
        processor = ContentProcessor({})
        with pytest.raises(NotImplementedError):
            processor.fetch_content()

    def test_organize_content_not_implemented(self):
        """Test that organize_content raises NotImplementedError."""
        processor = ContentProcessor({})
        with pytest.raises(NotImplementedError):
            processor.organize_content({'raw': 'data'})

    def test_save_content_not_implemented(self):
        """Test that save_content raises NotImplementedError."""
        processor = ContentProcessor({})
        with pytest.raises(NotImplementedError):
            processor.save_content({'organized': 'data'})


class TestRawContentProcessor:
    """Tests for RawContentProcessor class."""

    @pytest.fixture
    def mock_webdav_client(self):
        """Create a mock WebDAV client."""
        return MagicMock()

    @pytest.fixture
    def mock_database(self):
        """Create a mock database client."""
        return MagicMock()

    @pytest.fixture
    def processor(self, mock_webdav_client, mock_database):
        """Create a RawContentProcessor instance with mocked dependencies."""
        return RawContentProcessor(
            webdav_client=mock_webdav_client,
            source_dir='/raw-content',
            dest_dir='/processed-content',
            database=mock_database
        )

    def test_init(self, processor, mock_webdav_client, mock_database):
        """Test RawContentProcessor initialization."""
        assert processor.webdav_client == mock_webdav_client
        assert processor.source_dir == '/raw-content'
        assert processor.dest_dir == '/processed-content'
        assert processor.database == mock_database
        assert 'instagram' in processor.adapter_map

    def test_process_all_empty_directory(self, processor, mock_webdav_client):
        """Test processing when source directory is empty."""
        mock_webdav_client.list.return_value = []

        result = processor.process_all()

        assert result['status'] == 'success'
        assert result['processed_count'] == 0
        assert result['skipped_count'] == 0
        assert result['error_count'] == 0

    def test_process_all_with_json_files(self, processor, mock_webdav_client):
        """Test processing with JSON metadata files."""
        # Mock file listing
        mock_webdav_client.list.return_value = [
            {'name': 'post_123.json'},
            {'name': 'post_456.json'},
            {'name': 'image.jpg'},  # Should be skipped
        ]

        # Mock metadata reading
        metadata_1 = {
            'post_id': 'post_123',
            'username': 'testuser',
            'caption': 'Test post',
            'created_at': '2026-02-21T10:00:00',
            'source': 'instagram',
            'files': ['image_1.jpg', 'image_2.jpg']
        }
        metadata_2 = {
            'post_id': 'post_456',
            'username': 'testuser',
            'caption': 'Another post',
            'created_at': '2026-02-20T10:00:00',
            'source': 'instagram',
            'files': []
        }

        mock_webdav_client.read.side_effect = [
            json.dumps(metadata_1).encode(),
            json.dumps(metadata_2).encode(),
        ]

        # Mock mkdir and file operations
        mock_webdav_client.mkdir.return_value = None
        mock_webdav_client.write.return_value = None
        mock_webdav_client.delete.return_value = None

        result = processor.process_all()

        assert result['status'] == 'success'
        assert result['processed_count'] == 2
        assert result['skipped_count'] == 1  # image.jpg is skipped
        assert result['error_count'] == 0
        assert len(result['processed_items']) == 2

    def test_process_all_with_errors(self, processor, mock_webdav_client):
        """Test processing with invalid JSON files."""
        mock_webdav_client.list.return_value = [
            {'name': 'invalid.json'},
        ]

        # Mock invalid JSON reading
        mock_webdav_client.read.return_value = b'invalid json {{'

        result = processor.process_all()

        assert result['status'] == 'error'
        assert result['processed_count'] == 0
        assert result['error_count'] == 1
        assert len(result['errors']) > 0

    def test_process_single_post_success(self, processor, mock_webdav_client):
        """Test successful processing of a single post."""
        metadata_path = '/raw-content/post_123.json'
        filename = 'post_123.json'
        metadata = {
            'post_id': 'post_123',
            'username': 'testuser',
            'caption': 'Test caption',
            'created_at': '2026-02-21T10:00:00',
            'source': 'instagram',
            'files': ['image.jpg']
        }

        mock_webdav_client.read.return_value = json.dumps(metadata).encode()
        mock_webdav_client.mkdir.return_value = None
        mock_webdav_client.write.return_value = None

        result = processor._process_single_post(metadata_path, filename)

        assert result['status'] == 'success'
        assert result['data']['post_id'] == 'post_123'
        assert result['data']['source'] == 'instagram'
        assert 'processed-content/instagram/testuser' in result['data']['destination']

    def test_process_single_post_invalid_json(self, processor, mock_webdav_client):
        """Test processing with invalid JSON metadata."""
        metadata_path = '/raw-content/invalid.json'
        filename = 'invalid.json'

        mock_webdav_client.read.return_value = b'{invalid json'

        result = processor._process_single_post(metadata_path, filename)

        assert result['status'] == 'error'
        assert 'Invalid metadata format' in result['error']

    def test_create_destination_path(self, processor):
        """Test destination path creation with proper structure."""
        metadata = {
            'post_id': 'post_123',
            'username': 'testuser',
            'created_at': '2026-02-21T10:00:00'
        }

        path = processor._create_destination_path(metadata, 'instagram')

        assert 'processed-content/instagram' in path
        assert 'testuser' in path

    def test_create_destination_path_missing_fields(self, processor):
        """Test destination path creation with missing metadata fields."""
        metadata = {'post_id': 'post_123'}

        path = processor._create_destination_path(metadata, 'instagram')

        assert 'processed-content/instagram' in path
        assert 'unknown' in path

    def test_move_associated_files(self, processor, mock_webdav_client):
        """Test moving associated files to destination."""
        metadata = {
            'files': ['image1.jpg', 'image2.jpg']
        }
        dest_dir = '/processed-content/instagram/testuser'

        mock_webdav_client.read.side_effect = [b'image1_content', b'image2_content']
        mock_webdav_client.write.return_value = None
        mock_webdav_client.delete.return_value = None

        files_moved = processor._move_associated_files(metadata, dest_dir, 'instagram')

        assert files_moved == 2
        assert mock_webdav_client.write.call_count == 2
        assert mock_webdav_client.delete.call_count == 2

    def test_save_metadata(self, processor, mock_webdav_client):
        """Test metadata saving to destination."""
        dest_dir = '/processed-content/instagram/testuser'
        organized_data = {
            'post_id': 'post_123',
            'source': 'instagram',
            'username': 'testuser',
            'media_count': 2
        }

        mock_webdav_client.write.return_value = None

        processor._save_metadata(dest_dir, organized_data)

        # Verify metadata was written
        assert mock_webdav_client.write.called
        call_args = mock_webdav_client.write.call_args
        assert 'metadata.json' in call_args[0][0]


class TestInstagramRawAdapter:
    """Tests for InstagramRawAdapter class."""

    @pytest.fixture
    def mock_webdav_client(self):
        """Create a mock WebDAV client."""
        return MagicMock()

    @pytest.fixture
    def adapter(self, mock_webdav_client):
        """Create an InstagramRawAdapter instance."""
        metadata = {
            'post_id': 'post_123',
            'username': 'testuser',
            'caption': 'Test caption',
            'created_at': '2026-02-21T10:00:00',
            'source': 'instagram',
            'files': ['image1.jpg', 'image2.jpg']
        }
        return InstagramRawAdapter(metadata=metadata, webdav_client=mock_webdav_client)

    def test_init(self, adapter, mock_webdav_client):
        """Test InstagramRawAdapter initialization."""
        assert adapter.metadata['post_id'] == 'post_123'
        assert adapter.webdav_client == mock_webdav_client

    def test_organize(self, adapter):
        """Test metadata organization."""
        organized = adapter.organize()

        assert organized['post_id'] == 'post_123'
        assert organized['source'] == 'instagram'
        assert organized['username'] == 'testuser'
        assert organized['caption'] == 'Test caption'
        assert organized['media_count'] == 2
        assert 'raw_metadata' in organized

    def test_organize_minimal_metadata(self, mock_webdav_client):
        """Test organization with minimal metadata."""
        minimal_metadata = {
            'post_id': 'post_456',
            'source': 'instagram'
        }
        adapter = InstagramRawAdapter(metadata=minimal_metadata, webdav_client=mock_webdav_client)

        organized = adapter.organize()

        assert organized['post_id'] == 'post_456'
        assert organized['source'] == 'instagram'
        assert organized['username'] is None
        assert organized['media_count'] == 0


class TestRawContentProcessorConfigOverrides:
    """Tests for RawContentProcessor directory configuration overrides."""

    @pytest.fixture
    def mock_webdav_client(self):
        """Create a mock WebDAV client."""
        return MagicMock()

    @pytest.fixture
    def mock_database(self):
        """Create a mock database client."""
        mock_db = MagicMock()
        mock_db.get_completed_raw_content_paths.return_value = set()
        return mock_db

    @pytest.fixture
    def processor(self, mock_webdav_client, mock_database):
        """Create a RawContentProcessor instance with default directories."""
        return RawContentProcessor(
            webdav_client=mock_webdav_client,
            source_dir='/default-source',
            dest_dir='/default-dest',
            database=mock_database
        )

    def test_scan_with_source_dir_override(self, processor, mock_webdav_client, mock_database):
        """Test that scan_source respects source_dir_override parameter."""
        # Setup mock to return empty list
        mock_webdav_client.list.return_value = []

        # Call scan with override
        result = processor.scan_source(
            limit=50,
            offset=0,
            user_id='test_user',
            database=mock_database,
            source_dir_override='/custom-source'
        )

        # Verify that list was called with the override path, not the default
        mock_webdav_client.list.assert_called_once_with('/custom-source')
        assert result['status'] == 'success'

    def test_scan_without_override_uses_default(self, processor, mock_webdav_client, mock_database):
        """Test that scan_source uses instance default when no override provided."""
        # Setup mock to return empty list
        mock_webdav_client.list.return_value = []

        # Call scan without override
        result = processor.scan_source(
            limit=50,
            offset=0,
            user_id='test_user',
            database=mock_database
        )

        # Verify that list was called with the default path
        mock_webdav_client.list.assert_called_once_with('/default-source')
        assert result['status'] == 'success'

    def test_scan_with_both_overrides(self, processor, mock_webdav_client, mock_database):
        """Test that scan_source accepts both source and dest overrides."""
        # Setup mock to return empty list
        mock_webdav_client.list.return_value = []

        # Call scan with both overrides
        result = processor.scan_source(
            limit=50,
            offset=0,
            user_id='test_user',
            database=mock_database,
            source_dir_override='/custom-source',
            dest_dir_override='/custom-dest'
        )

        # Verify that list was called with the override path
        mock_webdav_client.list.assert_called_once_with('/custom-source')
        assert result['status'] == 'success'
