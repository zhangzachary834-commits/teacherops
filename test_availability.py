import unittest

import availability


class AvailabilityOverlapTests(unittest.TestCase):
    """Tests for schedule parsing and interval overlap math."""

    def test_tuesday_after_six_overlaps_tuesday_six(self):
        overlap = availability.availability_overlap(
            ["tuesday 6"],
            ["tuesday after 6"],
        )

        self.assertTrue(overlap)
        self.assertIn("tuesday", overlap[0])

    def test_friday_after_six_overlaps_friday_six(self):
        overlap = availability.availability_overlap(
            ["friday 6"],
            ["friday after 6"],
        )

        self.assertTrue(overlap)

    def test_no_overlap_for_different_days(self):
        overlap = availability.availability_overlap(
            ["tuesday after 6"],
            ["saturday"],
        )

        self.assertEqual(overlap, [])

    def test_every_day_range_overlaps_specific_day(self):
        overlap = availability.availability_overlap(
            ["tuesday 6"],
            ["every day at 5-8"],
        )

        self.assertTrue(overlap)
        self.assertIn("tuesday", overlap[0])

    def test_non_overlapping_times_on_same_day(self):
        overlap = availability.availability_overlap(
            ["tuesday 8am"],
            ["tuesday after 6"],
        )

        self.assertEqual(overlap, [])

    def test_evening_overlaps_after_six(self):
        overlap = availability.availability_overlap(
            ["tuesday evening"],
            ["tuesday after 6"],
        )

        self.assertTrue(overlap)

    def test_unparseable_entries_are_ignored(self):
        overlap = availability.availability_overlap(
            ["tuesday 6"],
            ["idk"],
        )

        self.assertEqual(overlap, [])

    def test_overlap_minutes_counts_shared_window(self):
        minutes = availability.overlap_minutes(
            ["tuesday 6"],
            ["tuesday after 6"],
        )

        self.assertGreater(minutes, 0)

    def test_weekend_expands_to_both_days(self):
        slots = availability.parse_availability(["weekend"])

        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].days, frozenset({5, 6}))


if __name__ == "__main__":
    unittest.main()
