import os
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from bot.utils.media import format_audio_tracks_summary, probe_audio_tracks, extract_audio_tracks, _probe_with_ffmpeg
from bot.database.mongo import db

def test_format_audio_tracks_summary():
    tracks = [
        {"audio_index": 0, "title": "English AAC", "language": "eng", "codec": "aac"},
        {"audio_index": 1, "title": "Hindi AC3", "language": "hin", "codec": "ac3"}
    ]
    summary = format_audio_tracks_summary(tracks)
    assert "Track 1" in summary
    assert "English AAC" in summary
    assert "Track 2" in summary
    assert "Hindi AC3" in summary

    empty_summary = format_audio_tracks_summary([])
    assert "None detected" in empty_summary

def test_probe_audio_tracks_nonexistent():
    async def _test():
        tracks = await probe_audio_tracks("non_existent_file.mkv")
        assert tracks == []
    asyncio.run(_test())

def test_probe_with_ffmpeg_fallback():
    async def _test():
        fake_stderr = (
            "Input #0, matroska, from 'test.mkv':\n"
            "  Stream #0:0: Video: h264\n"
            "  Stream #0:1(eng): Audio: aac, 44100 Hz, mono\n"
            "      Metadata:\n"
            "        title           : English Track\n"
            "  Stream #0:2(hin): Audio: ac3, 44100 Hz, mono\n"
            "      Metadata:\n"
            "        title           : Hindi Track\n"
        )
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", fake_stderr.encode())

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            tracks = await _probe_with_ffmpeg("ffmpeg", "test.mkv")
            assert len(tracks) == 2
            assert tracks[0]["title"] == "English Track"
            assert tracks[0]["language"] == "eng"
            assert tracks[1]["title"] == "Hindi Track"
            assert tracks[1]["language"] == "hin"

    asyncio.run(_test())

def test_mongo_media_file_crud():
    async def _test():
        mock_files = {}

        async def mock_update_one(query, update, upsert=False):
            file_id = query["file_id"]
            mock_files[file_id] = update["$set"]

        async def mock_find_one(query):
            if "file_id" in query:
                return mock_files.get(query["file_id"])
            if "chat_id" in query and "message_id" in query:
                for f in mock_files.values():
                    if f.get("chat_id") == query["chat_id"] and f.get("message_id") == query["message_id"]:
                        return f
            return None

        async def mock_delete_one(query):
            file_id = query.get("file_id")
            if file_id in mock_files:
                del mock_files[file_id]

        with patch.object(db.media_files, 'update_one', side_effect=mock_update_one), \
             patch.object(db.media_files, 'find_one', side_effect=mock_find_one), \
             patch.object(db.media_files, 'delete_one', side_effect=mock_delete_one):

            test_data = {
                "file_id": "test-uuid-123",
                "file_name": "sample.mkv",
                "file_path": "/tmp/sample.mkv",
                "file_size": 1024,
                "mime_type": "video/x-matroska",
                "chat_id": 12345,
                "message_id": 678,
                "audio_tracks": [{"audio_index": 0, "title": "Main Track"}]
            }

            await db.add_media_file(test_data)
            fetched = await db.get_media_file("test-uuid-123")
            assert fetched is not None
            assert fetched["file_name"] == "sample.mkv"

            by_msg = await db.get_media_file_by_message(12345, 678)
            assert by_msg is not None
            assert by_msg["file_id"] == "test-uuid-123"

            await db.delete_media_file("test-uuid-123")
            deleted = await db.get_media_file("test-uuid-123")
            assert deleted is None

    asyncio.run(_test())
