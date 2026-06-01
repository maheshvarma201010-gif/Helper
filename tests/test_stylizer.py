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
    # Verify URL is NOT stylized
    assert "https://example.com" in result
    assert "𝐡𝐭𝐭𝐩𝐬" not in result

    text_with_entity = "A &amp; B"
    result = stylize_text(text_with_entity, "bold")
    # Verify 'A' and 'B' are stylized but '&amp;' is NOT
    assert "𝐀" in result
    assert "𝐁" in result
    assert "&amp;" in result
    assert "&𝐚𝐦𝐩;" not in result
