"""Synthetic standalone checks; no database, network, GPU or user data."""
import base64
import json
import unittest
from unittest.mock import patch

from huanjing_agent_utils.queue_wait import normalize_queue_wait, project_queue_wait
from huanjing_agent_utils.history_pagination import (
    HistoryPageError, binding, canonical, date_bound, decode, encode, page_filters,
)


class QueueWaitTests(unittest.TestCase):
    def observation(self, **changes):
        return {
            'source': 'WORKER_SCHEDULER',
            'reason_code': 'GLOBAL_FIFO_PREDECESSOR',
            'checked_at': 1000,
            **changes,
        }

    def test_only_allowlisted_fields_reach_the_projection(self):
        value = self.observation(private_prompt='synthetic', path='not-public')
        self.assertEqual(normalize_queue_wait(value, now=1001), self.observation())

    def test_stale_future_nonfinite_and_untrusted_observations_are_rejected(self):
        for changes in (
            {'checked_at': 954}, {'checked_at': 1006},
            {'checked_at': float('nan')}, {'checked_at': True},
            {'source': 'CLIENT'}, {'reason_code': 'UNRECOGNIZED'},
        ):
            with self.subTest(changes=changes):
                self.assertIsNone(normalize_queue_wait(self.observation(**changes), now=1000))
        self.assertIsNone(normalize_queue_wait(None, now=1000))

    def test_numeric_ranges_do_not_coerce_strings_or_booleans(self):
        for changes in (
            {'gpu_index': True}, {'gpu_index': 65},
            {'free_vram_mib': '1024'}, {'available_ram_mib': -1},
        ):
            with self.subTest(changes=changes):
                self.assertIsNone(normalize_queue_wait(self.observation(**changes), now=1000))

    def test_timing_boundaries_are_inclusive(self):
        for stamp in (955, 1005):
            self.assertIsNotNone(normalize_queue_wait(self.observation(checked_at=stamp), now=1000))

    def test_projection_preserves_queue_position_and_wait_semantics(self):
        job = {'status': 'RUNNING', 'stage': 'QUEUED', 'queue_position': 2,
               'queue_wait_json': json.dumps(self.observation())}
        with patch('huanjing_agent_utils.queue_wait.time.time', return_value=1000):
            wait, message = project_queue_wait(job)
        self.assertEqual(wait, self.observation())
        self.assertIn('全局队列第 2 位', message)
        self.assertIn('等待前面的任务完成交付', message)

    def test_terminal_nonqueued_and_malformed_jobs_have_no_wait_projection(self):
        base = {'status': 'RUNNING', 'stage': 'QUEUED',
                'queue_wait_json': json.dumps(self.observation())}
        for changes in (
            {'status': 'FAILED'}, {'status': 'COMPLETED'}, {'status': 'CANCELLED'},
            {'stage': 'SYNTHESIZING'}, {'queue_wait_json': '{broken'},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(project_queue_wait({**base, **changes}), (None, None))


class PaginationTests(unittest.TestCase):
    def setUp(self):
        self.filters = page_filters({'q': '', 'sort': 'UPDATED_DESC'},
                                    page_size=20, date_from='', date_to='')
        self.scope = binding('synthetic-owner', self.filters)
        self.row = {'session_id': 'synthetic-session',
                    'updated_at': '2026-10-21T00:00:00+00:00'}
        self.cursor = encode(self.row, self.filters, self.scope, now=1000, token=None)

    def pack(self, raw):
        return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')

    def test_round_trip_and_empty_initial_cursor(self):
        value = decode(self.cursor, self.scope, now=1001)
        self.assertEqual(value['after'], {'time': self.row['updated_at'],
                                         'id': self.row['session_id']})
        self.assertIsNone(decode('', self.scope, now=1001))

    def test_owner_and_filter_changes_reject_the_old_position(self):
        scopes = (binding('other-owner', self.filters),
                  binding('synthetic-owner', {**self.filters, 'q': 'changed'}))
        for scope in scopes:
            with self.subTest(scope=scope), self.assertRaises(HistoryPageError):
                decode(self.cursor, scope, now=1001)

    def test_expiry_is_reported_without_renewing_the_cursor(self):
        token = decode(self.cursor, self.scope, now=1001)
        next_cursor = encode({**self.row, 'session_id': 'next-session'},
                             self.filters, self.scope, now=1500, token=token)
        self.assertEqual(decode(next_cursor, self.scope, now=1501)['expires_at'], 1900)
        with self.assertRaises(HistoryPageError) as caught:
            decode(next_cursor, self.scope, now=1900)
        self.assertEqual(caught.exception.code, 'HISTORY_CURSOR_EXPIRED')
        self.assertEqual(caught.exception.status_code, 409)

    def test_noncanonical_duplicate_and_unknown_fields_are_rejected(self):
        value = decode(self.cursor, self.scope, now=1001)
        duplicate = canonical(value).decode('utf-8').replace('"v":1', '"v":1,"v":1')
        candidates = (
            self.pack(json.dumps(value, indent=2).encode('utf-8')),
            self.pack(duplicate.encode('utf-8')),
            self.pack(canonical({**value, 'extra': True})),
            self.cursor + '==', 'a' * 2049,
        )
        for cursor in candidates:
            with self.subTest(cursor=cursor[:30]), self.assertRaises(HistoryPageError):
                decode(cursor, self.scope, now=1001)

    def test_invalid_stored_identifiers_never_enter_a_public_cursor(self):
        with self.assertRaises(HistoryPageError):
            encode({**self.row, 'session_id': '../private'},
                   self.filters, self.scope, now=1000, token=None)

    def test_page_size_query_controls_and_reversed_dates_are_rejected(self):
        for size in (True, 0, 21):
            with self.subTest(size=size), self.assertRaises(HistoryPageError):
                page_filters({'q': '', 'sort': 'UPDATED_DESC'},
                             page_size=size, date_from='', date_to='')
        with self.assertRaises(HistoryPageError):
            page_filters({'q': 'bad\x00query', 'sort': 'UPDATED_DESC'},
                         page_size=20, date_from='', date_to='')
        with self.assertRaises(HistoryPageError):
            page_filters({'q': '', 'sort': 'UPDATED_DESC'}, page_size=20,
                         date_from='2026-10-22T00:00:00Z',
                         date_to='2026-10-21T00:00:00Z')

    def test_dates_normalize_to_utc_and_nan_is_not_canonical_json(self):
        self.assertEqual(date_bound('2026-10-21T08:00:00+08:00'),
                         '2026-10-21T00:00:00+00:00')
        with self.assertRaises(ValueError):
            canonical({'invalid': float('nan')})


if __name__ == '__main__':
    unittest.main()
