"""
Shared ingestion helpers for WebUI and bot to parse links, validate, and enqueue posts/accounts.
This module is intentionally UI-agnostic: no Telegram or FastAPI dependencies.
"""
from datetime import datetime, timedelta
import re
from typing import Callable

from logger import log
from configs.constants import REGEX_SPECIFIC_LINK, REGEX_PROFILE_LINK


def _clean_url(url: str) -> str:
    return (url or '').split('?')[0].strip()


def _is_post_link(url: str) -> bool:
    return bool(re.match(REGEX_SPECIFIC_LINK, url or ''))


def _is_profile_link(url: str) -> bool:
    return bool(re.match(REGEX_PROFILE_LINK, url or ''))


def _extract_post_id(url: str) -> str:
    clean = _clean_url(url)
    parts = clean.split('/')
    return parts[4] if len(parts) > 4 else ''


def _extract_username(url: str) -> str:
    clean = _clean_url(url)
    parts = clean.split('/')
    return parts[3] if len(parts) > 3 else ''


def _validate_shortcode(post_id: str) -> bool:
    return len(post_id) == 11 and bool(re.match(r'^[a-zA-Z0-9_-]+$', post_id))


def _validate_username(username: str) -> bool:
    return bool(username) and bool(re.match(r'^[a-zA-Z0-9._]+$', username))


def _resolve_scheduled_time(rate_limit_fn: Callable[[], datetime | None]) -> datetime:
    rate_time = rate_limit_fn() if rate_limit_fn else None
    if rate_time and isinstance(rate_time, datetime):
        return rate_time
    return datetime.now()


def enqueue_links(
    urls: list[str],
    user_id: str,
    database,
    rate_limit_fn: Callable[[], datetime | None] = None,
    downloader=None,
    account_delay_minutes: int = 60,
    role_check_fn: Callable[[str], tuple[bool, str]] = None,
) -> dict:
    """
    Parse links, validate, check uniqueness, and enqueue posts/accounts.
    Returns {'success': [...], 'errors': [...]} with per-link details.

    Args:
        urls: List of Instagram URLs to process
        user_id: User ID submitting the links
        database: Database client
        rate_limit_fn: Callable that returns scheduled_time (datetime | None) for rate limiting
        downloader: Instagram downloader instance
        account_delay_minutes: Delay in minutes for account post ingestion
        role_check_fn: Callable that checks role permission for a link type.
                      Takes link_type ('post'|'account'), returns (allowed: bool, message: str)
    """
    results = {'success': [], 'errors': []}

    for idx, raw_url in enumerate(urls):
        try:
            if not raw_url or not raw_url.strip():
                results['errors'].append({'url': raw_url, 'error': 'Empty URL'})
                continue

            scheduled_time = _resolve_scheduled_time(rate_limit_fn)
            clean_url = _clean_url(raw_url)

            link_type = None
            post_id = None

            if _is_post_link(raw_url):
                link_type = 'post'
                post_id = _extract_post_id(clean_url)
                if not _validate_shortcode(post_id):
                    results['errors'].append({'url': raw_url, 'error': 'Invalid post shortcode format'})
                    continue

                # Check role permission for this post link
                if role_check_fn:
                    allowed, message = role_check_fn(link_type)
                    if not allowed:
                        results['errors'].append({'url': raw_url, 'error': message})
                        continue

                if not database.check_message_uniqueness(post_id=post_id, user_id=user_id):
                    results['errors'].append({'url': raw_url, 'error': 'Already in queue or processed'})
                    continue

                data = database.create_queue_message_data(
                    user_id=user_id,
                    post_id=post_id,
                    post_url=clean_url,
                    link_type=link_type,
                    message_id=f"ingestion_{post_id}",
                    chat_id=user_id,
                    scheduled_time=scheduled_time,
                    post_owner='undefined'
                )
                database.add_message_to_queue(data=data)
                results['success'].append({
                    'url': raw_url,
                    'post_id': post_id,
                    'scheduled_time': data['scheduled_time']
                })
                continue

            if _is_profile_link(raw_url):
                link_type = 'account'
                account_name = _extract_username(clean_url)
                if not _validate_username(account_name):
                    results['errors'].append({'url': raw_url, 'error': 'Invalid username format'})
                    continue

                # Check role permission for account link
                if role_check_fn:
                    allowed, message = role_check_fn(link_type)
                    if not allowed:
                        results['errors'].append({'url': raw_url, 'error': message})
                        continue

                if downloader is None:
                    results['errors'].append({'url': raw_url, 'error': 'Account ingestion not supported (downloader unavailable)'})
                    continue

                # Fetch account info / id
                account_id, cursor = database.get_account_info(username=account_name)
                if not account_id:
                    account_info = downloader.get_account_info(username=account_name)
                    database.add_account_info(data=account_info)
                    account_id = account_info['pk']
                    cursor = None

                processed_count = 0
                account_scheduled_time = scheduled_time + timedelta(minutes=account_delay_minutes)

                while True:
                    posts_list, cursor = downloader.get_account_posts(user_id=account_id, cursor=cursor)
                    for post in posts_list:
                        if database.check_message_uniqueness(post_id=post.code, user_id=user_id):
                            # For each post from account, recalculate scheduled_time with rate limit
                            post_scheduled_time = _resolve_scheduled_time(rate_limit_fn) + timedelta(minutes=account_delay_minutes)

                            data = database.create_queue_message_data(
                                user_id=user_id,
                                post_id=post.code,
                                post_url=f"https://www.instagram.com/{downloader.media_type_links[post.media_type]}/{post.code}",
                                link_type='account',
                                message_id=f"ingestion_{account_name}_{post.code}",
                                chat_id=user_id,
                                scheduled_time=post_scheduled_time,
                                post_owner=account_name
                            )
                            database.add_message_to_queue(data=data)
                            processed_count += 1
                    if not cursor:
                        break
                    database.add_account_info({'username': account_name, 'cursor': cursor})

                results['success'].append({
                    'url': raw_url,
                    'post_id': account_name,
                    'posts_added': processed_count,
                    'scheduled_time': account_scheduled_time.strftime('%Y-%m-%d %H:%M:%S')
                })
                log.info('[Ingestion]: User %s submitted account %s with %d posts', user_id, account_name, processed_count)
                continue

            results['errors'].append({'url': raw_url, 'error': 'Invalid Instagram URL'})

        except Exception as error:  # pylint: disable=broad-exception-caught
            log.error('[Ingestion]: Error processing link %d for user %s: %s', idx + 1, user_id, str(error))
            results['errors'].append({'url': raw_url, 'error': str(error)})

    return results
