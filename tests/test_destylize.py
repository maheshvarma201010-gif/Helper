from bot.utils.stylizer import destylize, stylize_text

def test_destylize():
    # 𝐀𝐛 -> Ab
    assert destylize("𝐀𝐛") == "Ab"
    # 𝒜𝒷 -> Ab
    assert destylize("𝒜𝒷") == "Ab"
    # <b>𝐇𝐞𝐥𝐥𝐨</b> -> <b>Hello</b>
    assert destylize("<b>𝐇𝐞𝐥𝐥𝐨</b>") == "<b>Hello</b>"

def test_restylize():
    # Bold -> Italic
    text = stylize_text("Hello", "bold") # <b>Hello</b>
    result = stylize_text(text, "italic")
    assert result == "<i>Hello</i>"

    # Unicode -> Bold
    text = stylize_text("Hello", "script") # ℋℯ𝓁𝓁ℴ
    result = stylize_text(text, "bold")
    assert result == "<b>Hello</b>"

def test_stylize_normal():
    # Bold -> Normal
    text = stylize_text("Hello", "bold")
    result = stylize_text(text, "normal")
    assert result == "Hello"
