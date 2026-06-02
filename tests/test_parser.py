import unittest
from bot.utils.parser import extract_metadata

class TestParser(unittest.TestCase):
    def test_advanced_formats(self):
        # Format 1: One Piece S22E1135 480p x264 WEB-DL Multi Audio ESub.mkv
        s, e, q, t = extract_metadata("One Piece S22E1135 480p x264 WEB-DL Multi Audio ESub.mkv")
        self.assertEqual(s, 22)
        self.assertEqual(e, 1135)
        self.assertEqual(q, "480p")
        self.assertEqual(t.lower(), "one piece")

        # Format 2: BEN 10 ALIEN FORCE - S01E12.mkv
        s, e, q, t = extract_metadata("BEN 10 ALIEN FORCE - S01E12.mkv")
        self.assertEqual(s, 1)
        self.assertEqual(e, 12)
        self.assertEqual(t.lower(), "ben 10 alien force")

        # Format 3: Wistoria: Wand and Sword S02E05 720p x265 10bit WEB-DL Multi Audio ESub.mkv
        s, e, q, t = extract_metadata("Wistoria: Wand and Sword S02E05 720p x265 10bit WEB-DL Multi Audio ESub.mkv")
        self.assertEqual(s, 2)
        self.assertEqual(e, 5)
        self.assertEqual(q, "720p")
        # Handle colon and other chars
        self.assertIn("wistoria", t.lower())

    def test_season_extraction(self):
        self.assertEqual(extract_metadata("Season 1")[0], 1)
        self.assertEqual(extract_metadata("S02")[0], 2)
        self.assertEqual(extract_metadata("S3")[0], 3)
        self.assertEqual(extract_metadata("1x05")[0], 1)

    def test_episode_extraction(self):
        self.assertEqual(extract_metadata("Episode 5")[1], 5)
        self.assertEqual(extract_metadata("EP10")[1], 10)
        self.assertEqual(extract_metadata("E01")[1], 1)
        self.assertEqual(extract_metadata("One Piece - 1135")[1], 1135)

    def test_quality_extraction(self):
        self.assertEqual(extract_metadata("720p")[2], "720p")
        self.assertEqual(extract_metadata("1080p")[2], "1080p")
        # In actual use, get_metadata handles the "Unknown" fallback
        self.assertIsNone(extract_metadata("nothing")[2])

if __name__ == '__main__':
    unittest.main()
