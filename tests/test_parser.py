import unittest
from bot.utils.parser import extract_metadata

class TestParser(unittest.TestCase):
    def test_season_extraction(self):
        self.assertEqual(extract_metadata("Season 1")[0], 1)
        self.assertEqual(extract_metadata("S02")[0], 2)
        self.assertEqual(extract_metadata("S3")[0], 3)

    def test_episode_extraction(self):
        self.assertEqual(extract_metadata("Episode 5")[1], 5)
        self.assertEqual(extract_metadata("EP10")[1], 10)
        self.assertEqual(extract_metadata("E01")[1], 1)

    def test_quality_extraction(self):
        self.assertEqual(extract_metadata("720p")[2], "720p")
        self.assertEqual(extract_metadata("1080p")[2], "1080p")
        self.assertEqual(extract_metadata("nothing")[2], "Unknown")

    def test_combined(self):
        s, e, q = extract_metadata("Season 01 Episode 05 720p")
        self.assertEqual(s, 1)
        self.assertEqual(e, 5)
        self.assertEqual(q, "720p")

        s, e, q = extract_metadata("S02E10 1080p")
        self.assertEqual(s, 2)
        self.assertEqual(e, 10)
        self.assertEqual(q, "1080p")

if __name__ == '__main__':
    unittest.main()
