import unittest
from bot.utils.replacer import replace_in_html

class TestReplacer(unittest.TestCase):
    def test_text_replacement(self):
        html = "Hello <b>World</b>"
        self.assertEqual(replace_in_html(html, "World", "Telegram"), "Hello <b>Telegram</b>")

    def test_link_replacement(self):
        html = '<a href="https://old.com">Link</a>'
        self.assertEqual(replace_in_html(html, "https://old.com", "https://new.com"), '<a href="https://new.com">Link</a>')

    def test_username_replacement(self):
        html = "Contact @olduser for info"
        self.assertEqual(replace_in_html(html, "@olduser", "@newuser"), "Contact @newuser for info")

if __name__ == '__main__':
    unittest.main()
