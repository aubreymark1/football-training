import datetime
import unittest
from league_schedule import FIXTURES, upcoming_matches


class FixturesTest(unittest.TestCase):
    def test_upcoming_includes_match_day_and_ends_after_season(self):
        self.assertEqual(len(FIXTURES), 10)
        first = upcoming_matches(datetime.date(2026, 11, 16))[0]
        self.assertEqual((first['date'], first['time'], first['away'], first['venue']),
                         ('2026-11-22', '15:20', '数学学院', '西区大球场'))
        self.assertEqual(upcoming_matches(datetime.date(2026, 11, 22))[0], first)
        self.assertEqual(upcoming_matches(datetime.date(2027, 5, 10)), [])


if __name__ == '__main__':
    unittest.main()
