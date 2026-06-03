from bot.utils.stylizer import stylize_text

def test_stylize_text_bold_button():
    # Buttons should still use Unicode
    result = stylize_text("Ab", "bold", is_button=True)
    assert result == "𝐀𝐛"

def test_stylize_text_bold_message():
    # Messages should use native HTML
    result = stylize_text("Ab", "bold", is_button=False)
    assert result == "<b>Ab</b>"

def test_stylize_text_italic_message():
    result = stylize_text("Ab", "italic", is_button=False)
    assert result == "<i>Ab</i>"

def test_stylize_text_mono_message():
    result = stylize_text("Ab", "mono", is_button=False)
    assert result == "<code>Ab</code>"

def test_stylize_text_bold_italic_message():
    result = stylize_text("Ab", "bold_italic", is_button=False)
    assert result == "<b><i>Ab</i></b>"

def test_stylize_text_script_message():
    # Script is not a native style, should use Unicode even in messages
    result = stylize_text("Ab", "script", is_button=False)
    assert "𝒜𝒷" in result or "𝓐𝓫" in result

def test_stylize_text_html_preservation_button():
    text = "<b>Hello</b> World"
    result = stylize_text(text, "bold", is_button=True)
    assert "<b>" in result
    assert "𝐇𝐞𝐥𝐥𝐨" in result

def test_stylize_usernames_button():
    text = "Follow @John_Doe"
    result = stylize_text(text, "bold", is_button=True)
    assert "𝐅𝐨𝐥𝐥𝐨𝐰" in result
    assert 'href="https://t.me/John_Doe"' in result
