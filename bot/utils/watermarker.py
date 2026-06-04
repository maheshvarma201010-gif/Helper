import os
from PIL import Image, ImageDraw, ImageFont, ImageOps

def apply_watermark(image_path, output_path, settings):
    """
    Applies a watermark to an image based on provided settings.
    settings: {
        "type": "logo" | "text" | "sticker",
        "content": "path_to_logo_or_sticker" | "text_string",
        "position": "top_left" | "top_center" | ... | "custom",
        "custom_x": int, "custom_y": int,
        "opacity": float (0-1),
        "size": int (percent of image width),
        "margin": int (pixels),
        "rotation": int (degrees)
    }
    """
    with Image.open(image_path).convert("RGBA") as base:
        width, height = base.size

        # Prepare watermark layer
        watermark_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))

        if settings["type"] in ["logo", "sticker"]:
            with Image.open(settings["content"]).convert("RGBA") as wm:
                # Scale
                scale_factor = settings.get("size", 10) / 100.0
                wm_width = int(width * scale_factor)
                aspect = wm.height / wm.width
                wm_height = int(wm_width * aspect)
                wm = wm.resize((wm_width, wm_height), Image.Resampling.LANCZOS)

                # Rotate
                if settings.get("rotation"):
                    wm = wm.rotate(settings["rotation"], expand=True)

                # Opacity
                if settings.get("opacity", 1.0) < 1.0:
                    alpha = wm.split()[3]
                    alpha = alpha.point(lambda p: p * settings["opacity"])
                    wm.putalpha(alpha)

                # Position
                x, y = calculate_position(width, height, wm.width, wm.height, settings)
                watermark_layer.paste(wm, (x, y), wm)

        elif settings["type"] == "text":
            draw = ImageDraw.Draw(watermark_layer)
            # Find a font
            font_size = int(width * (settings.get("size", 10) / 100.0))
            try:
                font = ImageFont.truetype("bot/web/static/fonts/Rajdhani-Bold.ttf", font_size)
            except:
                font = ImageFont.load_default()

            text = settings["content"]
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

            x, y = calculate_position(width, height, tw, th, settings)

            # Opacity for text
            fill_color = (255, 255, 255, int(255 * settings.get("opacity", 1.0)))
            draw.text((x, y), text, font=font, fill=fill_color)

        # Composite
        out = Image.alpha_composite(base, watermark_layer)

        # Preserve original format or save as PNG/JPG
        final_out = out.convert("RGB") if image_path.lower().endswith((".jpg", ".jpeg")) else out
        final_out.save(output_path, quality=95)

def calculate_position(img_w, img_h, wm_w, wm_h, settings):
    pos = settings.get("position", "bottom_right")
    margin = settings.get("margin", 20)

    if pos == "custom":
        return settings.get("custom_x", 0), settings.get("custom_y", 0)

    # Horizontal
    if "left" in pos:
        x = margin
    elif "center" in pos and "top_center" != pos and "bottom_center" != pos:
        x = (img_w - wm_w) // 2
    elif "right" in pos:
        x = img_w - wm_w - margin
    else: # top_center or bottom_center
        x = (img_w - wm_w) // 2

    # Vertical
    if "top" in pos:
        y = margin
    elif "center" in pos and "center_left" != pos and "center_right" != pos:
        y = (img_h - wm_h) // 2
    elif "bottom" in pos:
        y = img_h - wm_h - margin
    else: # center_left or center_right
        y = (img_h - wm_h) // 2

    if pos == "center":
        x = (img_w - wm_w) // 2
        y = (img_h - wm_h) // 2

    return x, y
