from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import os
import io
import logging

logger = logging.getLogger(__name__)

# Increase decompression bomb limit for large images
Image.MAX_IMAGE_PIXELS = None

def apply_watermark(image_path, settings, watermark_media_path=None):
    """
    Applies a watermark to an image based on settings.
    settings: dict containing type, position, opacity, size, margin, rotation, text (if type is text)
    """
    try:
        base_image = Image.open(image_path).convert("RGBA")
        width, height = base_image.size

        watermark_type = settings.get("type", "text")
        opacity = settings.get("opacity", 1.0)
        size_percent = settings.get("size", 10) / 100.0
        margin = settings.get("margin", 20)
        rotation = settings.get("rotation", 0)
        position = settings.get("position", "bottom_right")

        watermark_layer = Image.new("RGBA", base_image.size, (0, 0, 0, 0))

        if watermark_type in ["logo", "sticker"] and watermark_media_path:
            mark = Image.open(watermark_media_path).convert("RGBA")

            # Scale mark
            mark_width = int(width * size_percent)
            aspect_ratio = mark.height / mark.width
            mark_height = int(mark_width * aspect_ratio)
            mark = mark.resize((mark_width, mark_height), Image.Resampling.LANCZOS)

        elif watermark_type == "text":
            text = settings.get("text", "Watermark")
            # Try to use a default font or fallback
            try:
                # Common linux font paths
                font_paths = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/TTF/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
                ]
                font_path = next((p for p in font_paths if os.path.exists(p)), None)

                # Approximate font size based on image width and settings
                font_size = int(width * size_percent)
                if font_path:
                    font = ImageFont.truetype(font_path, font_size)
                else:
                    font = ImageFont.load_default()
            except Exception as e:
                logger.warning(f"Could not load font, using default: {e}")
                font = ImageFont.load_default()

            # Get text size
            draw = ImageDraw.Draw(watermark_layer)
            left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
            mark_width = right - left
            mark_height = bottom - top

            mark = Image.new("RGBA", (mark_width, mark_height), (0, 0, 0, 0))
            draw_mark = ImageDraw.Draw(mark)
            draw_mark.text((0, 0), text, font=font, fill=(255, 255, 255, 255))
        else:
            # Save to bytes even if no watermark applied
            output = io.BytesIO()
            final_image = base_image.convert("RGB")
            final_image.save(output, format="JPEG", quality=95)
            output.seek(0)
            return output

        # Apply rotation
        if rotation:
            mark = mark.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
            mark_width, mark_height = mark.size

        # Apply opacity
        if opacity < 1.0:
            alpha = mark.split()[3]
            alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
            mark.putalpha(alpha)

        # Calculate position
        x, y = 0, 0

        if position == "top_left":
            x, y = margin, margin
        elif position == "top_center":
            x, y = (width - mark_width) // 2, margin
        elif position == "top_right":
            x, y = width - mark_width - margin, margin
        elif position == "center_left":
            x, y = margin, (height - mark_height) // 2
        elif position == "center":
            x, y = (width - mark_width) // 2, (height - mark_height) // 2
        elif position == "center_right":
            x, y = width - mark_width - margin, (height - mark_height) // 2
        elif position == "bottom_left":
            x, y = margin, height - mark_height - margin
        elif position == "bottom_center":
            x, y = (width - mark_width) // 2, height - mark_height - margin
        elif position == "bottom_right":
            x, y = width - mark_width - margin, height - mark_height - margin
        elif position == "custom":
            custom_x = settings.get("custom_x", 0)
            custom_y = settings.get("custom_y", 0)
            # Treat custom X/Y as percentages if between 0 and 100
            x = int(width * (custom_x / 100.0)) if 0 <= custom_x <= 100 else custom_x
            y = int(height * (custom_y / 100.0)) if 0 <= custom_y <= 100 else custom_y

        # Composite
        base_image.paste(mark, (x, y), mark)

        # Save to bytes
        output = io.BytesIO()
        final_image = base_image.convert("RGB")
        final_image.save(output, format="JPEG", quality=95)
        output.seek(0)
        return output

    except Exception as e:
        logger.error(f"Error applying watermark: {e}")
        return None
