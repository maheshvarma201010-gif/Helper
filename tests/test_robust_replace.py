from bot.utils.replacer import replace_in_html
from bot.utils.stylizer import stylize_text

def test_replace_stylized():
    old_text = "google.com"
    new_text = "bing.com"

    # 1. Test stylized text
    stylized = stylize_text(old_text, "bold")
    html_input = f"Check this: {stylized}"
    replaced = replace_in_html(html_input, old_text, new_text)
    print(f"Stylized input: {html_input}")
    print(f"Replaced: {replaced}")
    assert new_text in replaced

def test_replace_hyperlink():
    old_text = "google.com"
    new_text = "bing.com"

    # 2. Test text inside hyperlink
    html_input = f'<a href="https://{old_text}">Visit {old_text}</a>'
    replaced = replace_in_html(html_input, old_text, new_text)
    print(f"Hyperlink input: {html_input}")
    print(f"Replaced: {replaced}")
    assert f'href="https://{new_text}"' in replaced
    assert f"Visit {new_text}" in replaced

def test_replace_case_insensitive():
    old_text = "Google.Com"
    new_text = "bing.com"

    html_input = "Visit google.com today"
    replaced = replace_in_html(html_input, old_text, new_text)
    print(f"Case-insensitive input: {html_input}")
    print(f"Replaced: {replaced}")
    assert new_text in replaced

def test_replace_unicode_stylized():
    old_text = "google.com"
    new_text = "bing.com"

    # Use stylize_text to generate a proper test input
    unicode_stylized = stylize_text(old_text, "sans_bold")
    html_input = f"Check this: {unicode_stylized}"
    replaced = replace_in_html(html_input, old_text, new_text)
    print(f"Unicode Stylized input: {html_input}")
    print(f"Replaced: {replaced}")
    assert new_text in replaced

if __name__ == "__main__":
    test_replace_stylized()
    test_replace_unicode_stylized()
    test_replace_hyperlink()
    test_replace_case_insensitive()
    print("All tests passed!")
