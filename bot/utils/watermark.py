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

            # Scale mark: Ensure size_percent actually changes dimensions
            mark_width = int(width * size_percent)
            if mark_width < 10: mark_width = 10 # Minimum size
            aspect_ratio = mark.height / mark.width
            mark_height = int(mark_width * aspect_ratio)
            mark = mark.resize((mark_width, mark_height), Image.Resampling.LANCZOS)
            logger.info(f"Scaled sticker/logo to {mark_width}x{mark_height} (size_percent={size_percent})")

        elif watermark_type == "text":
            text = settings.get("text", "Watermark")
            # Approximate font size based on image width and settings
            font_size = int(width * size_percent)
            if font_size < 10: font_size = 10 # Minimum font size

            # Try to use a default font or fallback
            try:
                # Common linux font paths including Docker-specific ones
                font_paths = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
                    "/usr/share/fonts/TTF/DejaVuSans.ttf",
                    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"
                ]
                font_path = next((p for p in font_paths if os.path.exists(p)), None)

                if font_path:
                    font = ImageFont.truetype(font_path, font_size)
                    logger.info(f"Loaded font {font_path} at size {font_size}")
                else:
                    # Pillow 10.1.0+ supports size in load_default()
                    font = ImageFont.load_default(size=font_size)
                    logger.info(f"Using default font at size {font_size}")
            except Exception as e:
                logger.warning(f"Could not load custom font, using default: {e}")
                try:
                    font = ImageFont.load_default(size=font_size)
                except:
                    font = ImageFont.load_default()

            # Get text size
            draw = ImageDraw.Draw(watermark_layer)
            left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
            mark_width = right - left
            mark_height = bottom - top

            # Ensure text has some dimension
            if mark_width <= 0: mark_width = 1
            if mark_height <= 0: mark_height = 1

            mark = Image.new("RGBA", (mark_width, mark_height), (0, 0, 0, 0))
            draw_mark = ImageDraw.Draw(mark)
            # Offset the text by the bounding box top/left to ensure it's fully visible
            draw_mark.text((-left, -top), text, font=font, fill=(255, 255, 255, 255))
            logger.info(f"Generated text watermark '{text}' at {mark_width}x{mark_height}")
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

        # Try to preserve EXIF data if present
        exif = base_image.info.get("exif")
        if exif:
            final_image.save(output, format="JPEG", quality=95, exif=exif)
        else:
            final_image.save(output, format="JPEG", quality=95)

        output.seek(0)
        return output

    except Exception as e:
        logger.error(f"Error applying watermark: {e}")
        return None
