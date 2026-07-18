import pytest
from bot.handlers.replace import get_progress_bar, format_duration
from bot.utils.replacer import replace_in_html, replace_in_buttons
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def test_progress_bar():
    assert get_progress_bar(0) == "░░░░░░░░░░░░░░░"
    assert get_progress_bar(100) == "███████████████"

    bar_50 = get_progress_bar(50)
    assert len(bar_50) == 15
    assert bar_50.count("█") in [7, 8]
    assert bar_50.count("░") in [7, 8]

def test_format_duration():
    assert format_duration(-1) == "--:--"
    assert format_duration(0) == "00:00"
    assert format_duration(5) == "00:05"
    assert format_duration(65) == "01:05"
    assert format_duration(3605) == "01:00:05"

def test_multi_target_replacement():
    targets = [
        "https://anizoneflixback.onrender.com",
        "old-domain.com",
        "AnimeZone",
        "@OldChannel"
    ]
    replacement = "https://anizoneflix-u00w.onrender.com"

    html_input = (
        "Check out AnimeZone for cool stuff! "
        "Visit https://anizoneflixback.onrender.com or old-domain.com. "
        "Follow us at @OldChannel."
    )

    result = html_input
    for target in targets:
        result = replace_in_html(result, target, replacement)

    # All of them should be replaced with the replacement string
    assert "AnimeZone" not in result
    assert "anizoneflixback.onrender.com" not in result
    assert "old-domain.com" not in result
    assert "@OldChannel" not in result
    assert result.count(replacement) == 4

def test_multi_target_buttons_replacement():
    targets = ["old_btn", "https://old-link.com"]
    replacement = "https://new-link.com"

    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("old_btn", url="https://old-link.com"),
            InlineKeyboardButton("other_btn", url="https://other-link.com")
        ]
    ])

    new_markup = reply_markup
    for target in targets:
        new_markup = replace_in_buttons(new_markup, target, replacement)

    assert new_markup.inline_keyboard[0][0].text == "https://new-link.com"
    assert new_markup.inline_keyboard[0][0].url == "https://new-link.com"

    assert new_markup.inline_keyboard[0][1].text == "other_btn"
    assert new_markup.inline_keyboard[0][1].url == "https://other-link.com"
