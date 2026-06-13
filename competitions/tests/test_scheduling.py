from django.test import TestCase

from competitions.scheduling import parse_competition_start_at


class SchedulingTests(TestCase):
    def test_parse_date_string_to_start_of_day(self):
        parsed = parse_competition_start_at("2026-06-15")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.hour, 0)
        self.assertEqual(parsed.minute, 0)
        self.assertEqual(parsed.day, 15)
        self.assertEqual(parsed.month, 6)

    def test_parse_iso_datetime_normalizes_to_start_of_day(self):
        parsed = parse_competition_start_at("2026-06-15T14:30:00Z")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.hour, 0)
        self.assertEqual(parsed.minute, 0)

    def test_invalid_value_returns_none(self):
        self.assertIsNone(parse_competition_start_at("not-a-date"))
