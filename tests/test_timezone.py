import unittest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timedelta, timezone


def utc_to_beijing_str(utc_time_str, fmt='%Y-%m-%d %H:%M'):
    if not utc_time_str:
        return None
    try:
        s = utc_time_str.strip()
        if s.endswith('Z'):
            s = s[:-1]
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone(timedelta(hours=8)))
            return dt.strftime(fmt)
        return (dt + timedelta(hours=8)).strftime(fmt)
    except Exception:
        return utc_time_str


class TestTimezoneConversion(unittest.TestCase):

    def test_utc_z_format_converts_to_beijing(self):
        self.assertEqual(utc_to_beijing_str('2026-08-21T04:00:00Z'), '2026-08-21 12:00')

    def test_utc_z_with_microseconds(self):
        self.assertEqual(utc_to_beijing_str('2026-08-21T03:30:45.123456Z'), '2026-08-21 11:30')

    def test_naive_datetime_treated_as_utc(self):
        self.assertEqual(utc_to_beijing_str('2026-08-21T04:00:00'), '2026-08-21 12:00')

    def test_none_returns_none(self):
        self.assertIsNone(utc_to_beijing_str(None))

    def test_empty_string(self):
        self.assertIsNone(utc_to_beijing_str(''))

    def test_invalid_string_returns_original(self):
        bad = 'not-a-date'
        self.assertEqual(utc_to_beijing_str(bad), bad)

    def test_consistent_with_current_time(self):
        now_utc = datetime.utcnow()
        now_cn = now_utc + timedelta(hours=8)
        result = utc_to_beijing_str(now_utc.isoformat() + 'Z')
        expected = now_cn.strftime('%Y-%m-%d %H:%M')
        self.assertEqual(result, expected)

    def test_custom_format(self):
        result = utc_to_beijing_str('2026-08-21T04:00:00Z', fmt='%Y/%m/%d %H:%M:%S')
        self.assertEqual(result, '2026/08/21 12:00:00')

    def test_midnight_boundary(self):
        self.assertEqual(utc_to_beijing_str('2026-08-20T16:00:00Z'), '2026-08-21 00:00')

    def test_evening_utc(self):
        self.assertEqual(utc_to_beijing_str('2026-08-21T15:30:00Z'), '2026-08-21 23:30')


if __name__ == '__main__':
    unittest.main()
