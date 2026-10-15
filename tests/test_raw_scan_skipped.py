"""
Scan report for source directories left out of the raw content queue.

The fake WebDAV tree mirrors the real Firefox-extension source layout: one directory per post
shortcode with a metadata.txt, plus the leftovers that never make it into the queue.
"""
import pytest
from src.modules.content_processor import RawContentProcessor

SOURCE = 'data/instagram/__extension-ff'

META_OK = (
    "post_id: AAAAAAAAAA1\nusername: user_alpha\nurl: https://www.instagram.com/p/AAAAAAAAAA1/\n"
    "source: instagram\nfiles: [video_001.mp4]\n"
)
META_REEL = (
    "post_id: reel\nusername: user_beta\nurl: https://www.instagram.com/p/reel/\n"
    "source: instagram\nfiles: [video_001_1700000000001.mp4]\n"
)


class FakeWebdav:
    """Directories map to their entry names; files map to their bytes."""

    def __init__(self, tree: dict, files: dict):
        self.tree = tree
        self.files = files

    def list(self, path, get_info=False):  # pylint: disable=unused-argument
        if path not in self.tree:
            raise RuntimeError(f'Remote resource: {path} not found')
        # Like Nextcloud: the listing starts with the directory itself
        return [path.rsplit('/', 1)[-1] + '/'] + list(self.tree[path])

    def check(self, path):
        return path in self.tree or path in self.files

    def is_dir(self, path):
        return path in self.tree

    def info(self, path):
        return {'isdir': path in self.tree}

    def download_from(self, buff, remote_path):
        buff.write(self.files[remote_path].encode())


@pytest.fixture(name='scan')
def fixture_scan():
    tree = {
        SOURCE: ['AAAAAAAAAA1/', 'reel/', 'AAAAAAAAAA3/', 'AAAAAAAAAA2/', 'Done1234567/', 'stray.jpg', '.DS_Store'],
        f'{SOURCE}/AAAAAAAAAA1': ['metadata.txt', 'video_001.mp4'],
        f'{SOURCE}/reel': ['metadata.txt', 'video_001_1700000000001.mp4'],
        f'{SOURCE}/AAAAAAAAAA3': [],
        f'{SOURCE}/AAAAAAAAAA2': ['image_001.jpg', 'image_002.jpg'],
        f'{SOURCE}/Done1234567': [],
    }
    files = {
        f'{SOURCE}/AAAAAAAAAA1/metadata.txt': META_OK,
        f'{SOURCE}/reel/metadata.txt': META_REEL,
        f'{SOURCE}/stray.jpg': 'x',
    }
    database = type('DB', (), {'get_completed_raw_content_paths': lambda self, uid: {f'{SOURCE}/Done1234567'}})()
    processor = RawContentProcessor(webdav_client=FakeWebdav(tree, files), source_dir=SOURCE, dest_dir='data/instagram')
    return processor.scan_source(user_id='1', database=database)


def test_only_real_post_is_processable(scan):
    assert [c['post_id'] for c in scan['processable_items']] == ['AAAAAAAAAA1']


def test_every_left_out_entry_has_a_reason(scan):
    reasons = {e['item_name']: e['reason'] for e in scan['skipped_items']}
    assert reasons == {
        'reel': 'ambiguous_id',
        'AAAAAAAAAA3': 'empty',
        'AAAAAAAAAA2': 'no_metadata',
        'Done1234567': 'already_completed',
        'stray.jpg': 'not_directory',
    }
    # .DS_Store is counted as skipped but not reported
    assert scan['skipped_count'] == len(scan['skipped_items']) + 1


def test_ambiguous_bucket_keeps_owner_and_files(scan):
    reel = next(e for e in scan['skipped_items'] if e['reason'] == 'ambiguous_id')
    assert reel['post_owner'] == 'user_beta'
    assert reel['files'] == ['video_001_1700000000001.mp4']


def test_no_metadata_lists_its_files(scan):
    entry = next(e for e in scan['skipped_items'] if e['reason'] == 'no_metadata')
    assert entry['file_count'] == 2
    assert entry['item_path'] == f'{SOURCE}/AAAAAAAAAA2'


def test_provider_link_from_shortcode_dir_name():
    from src.modules.webui import WebUI  # pylint: disable=import-outside-toplevel
    link = WebUI._skipped_provider_url  # pylint: disable=protected-access
    assert link({'item_name': 'AAAAAAAAAA2', 'reason': 'no_metadata'}) == 'https://www.instagram.com/p/AAAAAAAAAA2/'
    assert link({'item_name': 'reel', 'reason': 'ambiguous_id', 'post_url': 'https://www.instagram.com/p/reel/'}) is None
    assert link({'item_name': 'AAAAAAAAAA3', 'reason': 'empty'}) is None
    assert link({'item_name': 'stray.jpg', 'reason': 'not_directory'}) is None


def test_owner_sort_is_whitelisted_and_case_insensitive():
    from src.modules.webui import WebUI  # pylint: disable=import-outside-toplevel
    order = WebUI._build_raw_queue_order  # pylint: disable=protected-access
    assert order('owner', 'asc') == "LOWER(NULLIF(TRIM(post_owner), '')) ASC NULLS FIRST, id ASC"
    assert order('owner', 'desc').startswith("LOWER(NULLIF(TRIM(post_owner), '')) DESC NULLS LAST")
    assert order('id; DROP TABLE x', 'asc') == 'id ASC'
