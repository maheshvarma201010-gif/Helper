import unittest
from bot.utils.replacer import replace_in_html, render_message_to_html
from pyrogram.types import MessageEntity
from pyrogram import enums

class TestSmartReplacer(unittest.TestCase):
    def test_protocol_agnostic_replacement(self):
        html = 'Watch here: <a href="http://old.com/link">Link</a>'
        # Even if user provides https, it should match http
        res = replace_in_html(html, "https://old.com/link", "https://new.com")
        self.assertIn("https://new.com", res)
        self.assertNotIn("old.com", res)

    def test_nested_entity_rendering(self):
        # Bold text containing a link
        text = "Click HERE"
        entities = [
            MessageEntity(type=enums.MessageEntityType.BOLD, offset=0, length=10),
            MessageEntity(type=enums.MessageEntityType.TEXT_LINK, offset=6, length=4, url="http://test.com")
        ]
        html = render_message_to_html(text, entities)
        # Expected: <b>Click <a href="http://test.com">HERE</a></b>
        self.assertEqual(html, '<b>Click <a href="http://test.com">HERE</a></b>')

    def test_case_insensitive_fallback(self):
        html = "Download from ANIZONE"
        res = replace_in_html(html, "anizone", "NEWZONE")
        self.assertEqual(res, "Download from NEWZONE")

if __name__ == '__main__':
    unittest.main()
