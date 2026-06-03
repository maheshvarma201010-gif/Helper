import sys
import os
from pyrogram.types import MessageEntity
from pyrogram import enums

# Mock some parts of the bot for testing
class MockEntity:
    def __init__(self, type, offset, length, url=None):
        self.type = type
        self.offset = offset
        self.length = length
        self.url = url

def test_replacer():
    print("Testing Replacer Logic...")
    from bot.utils.replacer import render_message_to_html, replace_in_html

    text = "Join our channel @mysite and visit mysite.com"
    entities = [
        MockEntity(enums.MessageEntityType.MENTION, 17, 7),
        MockEntity(enums.MessageEntityType.URL, 35, 10)
    ]

    html_output = render_message_to_html(text, entities)
    print(f"HTML: {html_output}")

    replaced_html = replace_in_html(html_output, "mysite.com", "newsite.cc")
    print(f"Replaced: {replaced_html}")

    if "newsite.cc" in replaced_html and "@mysite" in replaced_html:
        print("Replacer test PASSED")
    else:
        print("Replacer test FAILED")
        sys.exit(1)

def test_sorter():
    print("Testing Sorter Logic...")
    from bot.utils.sorter import sort_files

    files = [
        {"season": 1, "episode": 2, "quality": "1080p"},
        {"season": 2, "episode": 1, "quality": "480p"},
        {"season": 1, "episode": 1, "quality": "1080p"},
        {"season": 1, "episode": 1, "quality": "720p"},
    ]

    sorted_files = sort_files(files)

    # Expected order:
    # 1. S1 720p E1
    # 2. S1 1080p E1
    # 3. S1 1080p E2
    # 4. S2 480p E1

    expected = [
        (1, "720p", 1),
        (1, "1080p", 1),
        (1, "1080p", 2),
        (2, "480p", 1)
    ]

    for i, f in enumerate(sorted_files):
        print(f"S{f['season']} Q{f['quality']} E{f['episode']}")
        if (f['season'], f['quality'], f['episode']) != expected[i]:
            print(f"Mismatch at index {i}")
            sys.exit(1)

    print("Sorter test PASSED")

if __name__ == "__main__":
    # Add project root to sys.path
    sys.path.insert(0, os.getcwd())
    test_replacer()
    test_sorter()
