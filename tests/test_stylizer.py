import pytest
from bot.utils.stylizer import stylize_text

def test_stylize_text_normal():
    assert stylize_text("Hello World", "normal") == "Hello World"
    assert stylize_text("Hello World", None) == "Hello World"

def test_stylize_text_bold():
    # Bold 'A' is 0x1D400 (𝐀), 'a' is 0x1D41A (𝐚)
    # "Ab" -> 𝐀𝐛
    result = stylize_text("Ab", "bold")
    assert result == "𝐀𝐛"

def test_stylize_text_html_preservation():
    # <b>Hello</b> World -> <b>𝐇𝐞𝐥𝐥𝐨</b> 𝐖𝐨𝐫𝐥𝐝
    text = "<b>Hello</b> World"
    result = stylize_text(text, "bold")
    assert "<b>" in result
    assert "</b>" in result
    assert result.startswith("<b>")
    # Content should be stylized
    assert "𝐇𝐞𝐥𝐥𝐨" in result
    assert "𝐖𝐨𝐫𝐥𝐝" in result

def test_stylize_text_complex_html():
    text = '<a href="https://example.com">Click Me</a>'
    result = stylize_text(text, "bold")
    assert '<a href="https://example.com">' in result
    assert '</a>' in result
    assert "𝐂𝐥𝐢𝐜𝐤 𝐌𝐞" in result

def test_stylize_special_chars():
    # Script 'B' is 0x212C (ℬ)
    result = stylize_text("B", "script")
    assert result == "ℬ"

    # Italic 'h' is 0x210E (ℎ)
    result = stylize_text("h", "italic")
    assert result == "ℎ"

def test_stylize_url_and_entities_preservation():
    text = "Check this: https://example.com & more!"
    result = stylize_text(text, "bold")
    # Verify 'Check' is stylized
    assert "𝐂𝐡𝐞𝐜𝐤" in result
    # Verify URL is stylized but wrapped in <a> tag to stay clickable
    assert '<a href="https://example.com">' in result
    assert "𝐡𝐭𝐭𝐩𝐬://𝐞𝐱𝐚𝐦𝐩𝐥𝐞.𝐜𝐨𝐦" in result

    text_with_entity = "A &amp; B"
    result = stylize_text(text_with_entity, "bold")
    # Verify 'A' and 'B' are stylized but '&amp;' is NOT
    assert "𝐀" in result
    assert "𝐁" in result
    assert "&amp;" in result
    assert "&𝐚𝐦𝐩;" not in result

def test_stylize_nested_links():
    text = 'Visit <a href="https://google.com">Google</a> now'
    result = stylize_text(text, "bold")
    assert "𝐕𝗶𝐬𝗶𝐭" in result or "𝐕𝐢𝐬𝐢𝐭" in result
    assert '<a href="https://google.com">' in result
    assert "𝐆𝐨𝐨𝐠𝐥𝐞" in result
    assert "𝐧𝐨𝐰" in result

def test_stylize_usernames():
    text = "Follow @John_Doe for more"
    result = stylize_text(text, "bold")
    assert "𝐅𝐨𝐥𝐥𝐨𝐰" in result
    assert '<a href="https://t.me/John_Doe">@𝐉𝐨𝐡𝐧_𝐃𝐨𝐞</a>' in result
    assert "𝐟𝐨𝐫" in result
