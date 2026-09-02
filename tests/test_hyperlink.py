import unittest
from bot.utils.hyperlink import parse_format_input, insert_hyperlinks

class TestHyperlink(unittest.TestCase):
    def test_parse_format_input(self):
        text = """
        Multi Audio : https://example.com/multi1
        Multi Audio : https://example.com/multi2
        Telugu : https://example.com/telugu1
        Telugu - https://example.com/telugu2
        """
        mappings = parse_format_input(text)
        expected = [
            ("Multi Audio", "https://example.com/multi1"),
            ("Multi Audio", "https://example.com/multi2"),
            ("Telugu", "https://example.com/telugu1"),
            ("Telugu", "https://example.com/telugu2")
        ]
        self.assertEqual(mappings, expected)

    def test_insert_hyperlinks_sequential(self):
        caption = "📥 ➤ Multi Audio | Telugu (480p)\n📥 ➤ Multi Audio | Telugu (720p)"
        mappings = [
            ("Multi Audio", "https://link1.com"),
            ("Multi Audio", "https://link2.com"),
            ("Telugu", "https://link3.com"),
            ("Telugu", "https://link4.com")
        ]
        result, extra, missing = insert_hyperlinks(caption, mappings)
        expected = (
            '📥 ➤ <a href="https://link1.com">Multi Audio</a> | <a href="https://link3.com">Telugu</a> (480p)\n'
            '📥 ➤ <a href="https://link2.com">Multi Audio</a> | <a href="https://link4.com">Telugu</a> (720p)'
        )
        self.assertEqual(result, expected)
        self.assertEqual(extra, [])
        self.assertEqual(missing, [])

    def test_extra_links_reporting(self):
        caption = "Multi Audio Telugu"
        mappings = [
            ("Multi Audio", "https://link1.com"),
            ("Multi Audio", "https://link2.com")
        ]
        result, extra, missing = insert_hyperlinks(caption, mappings)
        self.assertEqual(len(extra), 1)
        target, unused = extra[0]
        self.assertEqual(target, "Multi Audio")
        self.assertEqual(unused, ["https://link2.com"])

    def test_missing_links_reporting(self):
        caption = "Multi Audio Multi Audio Multi Audio"
        mappings = [
            ("Multi Audio", "https://link1.com")
        ]
        result, extra, missing = insert_hyperlinks(caption, mappings)
        self.assertEqual(len(missing), 1)
        target, total_occs, provided_count = missing[0]
        self.assertEqual(target, "Multi Audio")
        self.assertEqual(total_occs, 3)
        self.assertEqual(provided_count, 1)

if __name__ == "__main__":
    unittest.main()
