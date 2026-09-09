import os
import re
import json
import shutil
import asyncio
import logging

logger = logging.getLogger(__name__)

def get_ffmpeg_cmd() -> str:
    """Returns path/executable for ffmpeg."""
    cmd = shutil.which("ffmpeg")
    if cmd:
        return cmd

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        logger.warning(f"imageio_ffmpeg not available: {e}")

    return "ffmpeg"

def get_ffprobe_cmd() -> str | None:
    """Returns path/executable for ffprobe if available."""
    cmd = shutil.which("ffprobe")
    if cmd:
        return cmd
    return None

async def probe_audio_tracks(file_path: str) -> list[dict]:
    """
    Detects all audio tracks in the given video file using ffprobe or ffmpeg fallback.
    Returns a list of dicts with details of each audio track.
    """
    if not os.path.exists(file_path):
        logger.error(f"File not found for probing: {file_path}")
        return []

    ffprobe_exe = get_ffprobe_cmd()
    if ffprobe_exe:
        tracks = await _probe_with_ffprobe(ffprobe_exe, file_path)
        if tracks:
            return tracks

    # Fallback to ffmpeg -i parsing
    ffmpeg_exe = get_ffmpeg_cmd()
    return await _probe_with_ffmpeg(ffmpeg_exe, file_path)

async def _probe_with_ffprobe(ffprobe_exe: str, file_path: str) -> list[dict]:
    cmd = [
        ffprobe_exe,
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
            logger.warning(f"ffprobe returned non-zero code: {stderr.decode()}")
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
        logger.exception(f"Error in _probe_with_ffprobe: {e}")
        return []

async def _probe_with_ffmpeg(ffmpeg_exe: str, file_path: str) -> list[dict]:
    cmd = [ffmpeg_exe, "-i", file_path]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        output = stderr.decode(errors="ignore")
        audio_streams = []
        lines = output.splitlines()
        current_stream = None

        stream_pattern = re.compile(r'Stream #0:(\d+)(?:\(([^)]+)\))?: Audio: (\w+)')
        title_pattern = re.compile(r'^\s*title\s*:\s*(.+)$', re.IGNORECASE)

        for line in lines:
            m = stream_pattern.search(line)
            if m:
                if current_stream:
                    audio_streams.append(current_stream)
                stream_idx = int(m.group(1))
                lang = m.group(2) or "und"
                codec = m.group(3)
                current_stream = {
                    "stream_index": stream_idx,
                    "audio_index": len(audio_streams),
                    "codec": codec,
                    "channels": 2,
                    "language": lang,
                    "title": f"Audio Track {len(audio_streams) + 1}"
                }
            elif current_stream:
                tm = title_pattern.search(line)
                if tm:
                    current_stream["title"] = tm.group(1).strip()
                elif "Stream #" in line:
                    audio_streams.append(current_stream)
                    current_stream = None

        if current_stream:
            audio_streams.append(current_stream)

        return audio_streams

    except Exception as e:
        logger.exception(f"Error in _probe_with_ffmpeg: {e}")
        return []

async def extract_audio_tracks(file_path: str, output_dir: str) -> list[dict]:
    """
    Detects and extracts all audio tracks from file_path into output_dir using FFmpeg.
    Returns list of track dicts including extracted relative audio file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    tracks = await probe_audio_tracks(file_path)

    if not tracks:
        logger.info(f"No audio tracks detected or probing failed for {file_path}")
        return []

    ffmpeg_exe = get_ffmpeg_cmd()
    extracted_tracks = []

    for track in tracks:
        rel_idx = track["audio_index"]

        # We save extracted tracks as standard web-supported AAC/M4A audio format
        audio_filename = f"audio_track_{rel_idx}.aac"
        output_audio_path = os.path.join(output_dir, audio_filename)

        # Attempt re-encoding to AAC for guaranteed HTML5 browser playback
        cmd = [
            ffmpeg_exe,
            "-y",
            "-i", file_path,
            "-map", f"0:a:{rel_idx}",
            "-c:a", "aac",
            "-b:a", "192k",
            output_audio_path
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        # Fallback to copy stream if AAC encoding encounters issues
        if proc.returncode != 0 or not os.path.exists(output_audio_path) or os.path.getsize(output_audio_path) == 0:
            logger.warning(f"AAC encoding failed for track {rel_idx}, attempting stream copy: {stderr.decode()}")
            cmd_copy = [
                ffmpeg_exe,
                "-y",
                "-i", file_path,
                "-map", f"0:a:{rel_idx}",
                "-c", "copy",
                output_audio_path
            ]
            proc_copy = await asyncio.create_subprocess_exec(
                *cmd_copy,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc_copy.communicate()

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
