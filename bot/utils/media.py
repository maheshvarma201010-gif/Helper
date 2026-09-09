import os
import json
import asyncio
import logging

logger = logging.getLogger(__name__)

async def probe_audio_tracks(file_path: str) -> list[dict]:
    """
    Uses ffprobe to detect all audio tracks in the given video file.
    Returns a list of dicts with details of each audio track.
    """
    if not os.path.exists(file_path):
        logger.error(f"File not found for probing: {file_path}")
        return []

    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index,codec_name,channels,sample_rate:stream_tags=language,title",
        "-of", "json",
        file_path
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.error(f"ffprobe failed: {stderr.decode()}")
            return []

        data = json.loads(stdout.decode())
        streams = data.get("streams", [])
        tracks = []

        for rel_idx, stream in enumerate(streams):
            tags = stream.get("tags", {})
            lang = tags.get("language") or tags.get("LANGUAGE") or "und"
            title = tags.get("title") or tags.get("TITLE") or f"Audio Track {rel_idx + 1}"
            codec = stream.get("codec_name", "unknown")
            channels = stream.get("channels", 2)

            tracks.append({
                "stream_index": stream.get("index", rel_idx),
                "audio_index": rel_idx,
                "codec": codec,
                "channels": channels,
                "language": lang,
                "title": title
            })

        return tracks

    except Exception as e:
        logger.exception(f"Error probing audio tracks for {file_path}: {e}")
        return []

async def extract_audio_tracks(file_path: str, output_dir: str) -> list[dict]:
    """
    Detects and extracts all audio tracks from file_path into output_dir using FFmpeg.
    Returns list of track dicts including extracted relative audio file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    tracks = await probe_audio_tracks(file_path)

    if not tracks:
        logger.info(f"No audio tracks detected or ffprobe failed for {file_path}")
        return []

    extracted_tracks = []

    for track in tracks:
        rel_idx = track["audio_index"]
        codec = track["codec"]
        # Determine extension based on codec
        ext = "aac"
        if codec in ["mp3", "ac3", "eac3", "flac", "wav", "ogg"]:
            ext = codec

        audio_filename = f"audio_track_{rel_idx}.{ext}"
        output_audio_path = os.path.join(output_dir, audio_filename)

        # First attempt stream copy
        cmd = [
            "ffmpeg",
            "-y",
            "-i", file_path,
            "-map", f"0:a:{rel_idx}",
            "-c", "copy",
            output_audio_path
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        # If copy mode fails, attempt encoding to AAC
        if proc.returncode != 0 or not os.path.exists(output_audio_path) or os.path.getsize(output_audio_path) == 0:
            logger.warning(f"Copy stream failed for track {rel_idx}, falling back to AAC encoding.")
            audio_filename = f"audio_track_{rel_idx}.aac"
            output_audio_path = os.path.join(output_dir, audio_filename)
            fallback_cmd = [
                "ffmpeg",
                "-y",
                "-i", file_path,
                "-map", f"0:a:{rel_idx}",
                "-c:a", "aac",
                "-b:a", "192k",
                output_audio_path
            ]
            fallback_proc = await asyncio.create_subprocess_exec(
                *fallback_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await fallback_proc.communicate()

        if os.path.exists(output_audio_path) and os.path.getsize(output_audio_path) > 0:
            track_info = dict(track)
            track_info["file_name"] = audio_filename
            track_info["file_path"] = output_audio_path
            extracted_tracks.append(track_info)

    return extracted_tracks

def format_audio_tracks_summary(tracks: list[dict]) -> str:
    """Formats audio tracks into a neat text summary for Telegram messages."""
    if not tracks:
        return "🔊 **Audio Tracks:** None detected / single default track"

    summary = ["🔊 **Detected Audio Tracks:**"]
    for t in tracks:
        num = t.get("audio_index", 0) + 1
        title = t.get("title", f"Track {num}")
        lang = t.get("language", "und").upper()
        codec = t.get("codec", "aac").upper()
        summary.append(f"• **Track {num}:** {title} ({lang} | {codec})")

    return "\n".join(summary)
