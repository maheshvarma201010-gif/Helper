import unittest
from bot.utils.sorter import sort_files

class TestSorter(unittest.TestCase):
    def test_sorting_priority(self):
        files = [
            {"id": 1, "season": 1, "episode": 2, "quality": "1080p"},
            {"id": 2, "season": 1, "episode": 1, "quality": "1080p"},
            {"id": 3, "season": 2, "episode": 1, "quality": "480p"},
            {"id": 4, "season": 1, "episode": 1, "quality": "480p"},
        ]

        # Expected:
        # S1, 480p, E1 (id 4)
        # S1, 1080p, E1 (id 2)
        # S1, 1080p, E2 (id 1)
        # S2, 480p, E1 (id 3)

        sorted_files = sort_files(files)

        self.assertEqual(sorted_files[0]["id"], 4)
        self.assertEqual(sorted_files[1]["id"], 2)
        self.assertEqual(sorted_files[2]["id"], 1)
        self.assertEqual(sorted_files[3]["id"], 3)

if __name__ == '__main__':
    unittest.main()
