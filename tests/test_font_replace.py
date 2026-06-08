from bot.utils.replacer import replace_in_html
from bot.utils.stylizer import destylize

def test_complex_font_replace():
    # The stylized text provided by user
    stylized_input = "🏁 𝟭-𝟴 𝗦𝗲𝗮𝘀𝗼𝗻&#𝘅𝟮𝟳;𝘀 𝗔𝗱𝗱𝗲𝗱!\n\n🎬 𝗧𝗶𝘁𝗹𝗲: 𝗠𝘆 𝗛𝗲𝗿𝗼 𝗔𝗰𝗮𝗱𝗲𝗺𝗶𝗮 \n🗣 𝗚𝗲𝗻𝗿𝗲: 𝗦𝘂𝗽𝗲𝗿𝗻𝗮𝘁𝘂𝗿𝗮𝗹,𝗖𝗼𝗺𝗲𝗱𝘆,𝗠𝗮𝗻𝗴𝗮\n🔊 𝗔𝘂𝗱𝗶𝗼: 𝗛𝗶𝗻𝗱𝗶 • 𝗧𝗮𝗺𝗶𝗹 • 𝗧𝗲𝗹𝘂𝗴𝘂 • 𝗘𝗻𝗴𝗹𝗶𝘀𝗵 • 𝗝𝗮𝗽𝗮𝗻𝗲𝘀𝗲\n💬 𝗦𝘂𝗯𝘁𝗶𝘁𝗹𝗲: 𝗘𝗻𝗴𝗹𝗶𝘀𝗵\n📺 𝗤𝘂𝗮𝗹𝗶𝘁𝘆: 𝟰𝟴𝟬𝗽 𝗔𝗩𝗖 • 𝟳𝟮𝟬𝗽 𝗛𝗘𝗩𝗖/𝗔𝗩𝗖 • 𝟭𝟬𝟴𝟬𝗽 𝗛𝗘𝗩𝗖/𝗛𝗤\n🎙 𝗗𝘂𝗯 𝗕𝘆: 𝗖𝗮𝗿𝘁𝗼𝗼𝗻 𝗡𝗲𝘁𝘄𝗼𝗿𝗸\n\n📥 𝗪𝗮𝘁𝗰𝗵 / 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱\n👉𝗵𝘁𝘁𝗽𝘀://𝗮𝗻𝗶𝘇𝗼𝗻𝗲𝗳𝗹𝗶𝘅-𝗴𝗿𝗲𝘀.𝗼𝗻𝗿𝗲𝗻𝗱𝗲𝗿.𝗰𝗼𝗺/𝗮𝗻𝗶𝗺𝗲/𝗺𝘆-𝗵𝗲𝗿𝗼-𝗮𝗰𝗮𝗱𝗲𝗺𝗶𝗮-𝗺𝘂𝗹𝘁𝗶-𝗮𝘂𝗱𝗶𝗼-𝗰𝗻𝗱𝘂𝗯"

    # Text inside hyperlink (simulated as HTML anchor tag)
    html_input = f'<a href="https://anizoneflix-gres.onrender.com/anime/my-hero-academia-multi-audio-cndub">{stylized_input}</a>'

    old_domain = "anizoneflix-gres.onrender.com"
    new_domain = "new-domain.com"

    replaced = replace_in_html(html_input, old_domain, new_domain)

    print(f"Original HTML contains old domain: {old_domain in html_input}")
    print(f"Replaced HTML contains new domain: {new_domain in replaced}")
    print(f"Replaced HTML contains old domain: {old_domain in replaced}")

    assert new_domain in replaced
    assert old_domain not in replaced

if __name__ == "__main__":
    test_complex_font_replace()
    print("Test Passed!")
