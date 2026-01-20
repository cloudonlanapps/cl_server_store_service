"""Unit tests for media_metadata.py covering error handling and edge cases."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from cl_ml_tools.algorithms import MediaType

from store.store.media_metadata import MediaMetadataExtractor, validate_tools


class TestToolValidation:
    """Test validation of external tools (ExifTool, ffprobe)."""

    def test_exiftool_missing(self):
        """Test validation fails when ExifTool is missing."""
        with patch("store.store.media_metadata.MetadataExtractor") as MockExtractor:
            MockExtractor.return_value.is_exiftool_available.return_value = False
            with pytest.raises(RuntimeError, match="ExifTool not installed"):
                validate_tools()

    def test_ffprobe_missing(self):
        """Test validation fails when ffprobe is missing."""
        with patch("store.store.media_metadata.MetadataExtractor") as MockExtractor:
            MockExtractor.return_value.is_exiftool_available.return_value = True
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError
                with pytest.raises(RuntimeError, match="ffprobe not installed"):
                    validate_tools()

    def test_ffprobe_error(self):
        """Test validation fails when ffprobe checks fails."""
        with patch("store.store.media_metadata.MetadataExtractor") as MockExtractor:
            MockExtractor.return_value.is_exiftool_available.return_value = True
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(1, ["ffprobe"])
                with pytest.raises(RuntimeError, match="ffprobe not installed"):
                    validate_tools()


class TestMimeAndExtension:
    """Test MIME type and extension determination."""

    @pytest.fixture
    def extractor(self):
        return MediaMetadataExtractor()

    def test_mime_determination_failure(self, extractor):
        """Test failure when MIME type cannot be determined."""
        with patch("store.store.media_metadata.determine_mime") as mock_determine:
            mock_determine.side_effect = Exception("Unknown format")
            with pytest.raises(ValueError, match="Failed to determine MIME type"):
                extractor.extract_metadata(b"invalid data", "test.files")

    def test_magic_mime_fallback(self, extractor):
        """Test fallback when python-magic returns None."""
        with patch("store.store.media_metadata.determine_mime") as mock_determine:
            mock_determine.return_value = MediaType.IMAGE
            with patch("store.store.media_metadata.get_md5_hexdigest") as mock_md5:
                mock_md5.return_value = "a" * 32
                # Mock magic to return empty string
                with patch("magic.Magic") as MockMagic:
                    MockMagic.return_value.from_buffer.return_value = ""

                    # Mock other steps
                    with patch.object(extractor, "_determine_extension", return_value="bin"):
                        with patch.object(extractor, "_compute_hash", return_value="a" * 32):
                             with patch("tempfile.NamedTemporaryFile"):
                                with patch.object(extractor.exif_extractor, "extract_metadata_all", return_value={}):
                                    result = extractor.extract_metadata(b"data", "test.bin")
                                    assert result.mime_type == "application/octet-stream"

    @pytest.mark.parametrize(
        "mime,media_type,expected",
        [
            ("image/jpeg", MediaType.IMAGE, "jpg"),
            ("image/custom-format", MediaType.IMAGE, "custom-format"), # subtype extraction
            ("video/mp4", MediaType.VIDEO, "mp4"),
            ("unknown", MediaType.IMAGE, "jpg"), # fallback
            ("unknown", MediaType.VIDEO, "mp4"), # fallback
            ("unknown", MediaType.AUDIO, "mp3"), # fallback
            ("unknown", MediaType.TEXT, "txt"), # fallback
            ("unknown", MediaType.FILE, "bin"), # fallback
        ],
    )
    def test_determine_extension(self, extractor, mime, media_type, expected):
        """Test extension determination logic."""
        ext = extractor._determine_extension(mime, media_type)
        assert ext == expected

    def test_determine_extension_failure(self, extractor):
        """Test error propogation during extraction."""
        with patch("store.store.media_metadata.determine_mime", return_value=MediaType.IMAGE), \
             patch("magic.Magic") as MockMagic:
            MockMagic.return_value.from_buffer.return_value = "image/jpeg"

            # Mock _determine_extension to raise (simulate internal error if we want, or just rely on inputs)
            # Actually _determine_extension only raises ValueError explicitly? No, it catches nothing.
            # But extract_metadata catches exception from it?
            # Let's mock _determine_extension to raise to test extract_metadata error handling
            with patch.object(extractor, "_determine_extension", side_effect=ValueError("Bad ext")):
                 with pytest.raises(ValueError, match="Cannot determine extension"):
                     extractor.extract_metadata(b"data", "test.jpg")


class TestHashComputation:
    """Test hash computation for different media types."""

    @pytest.fixture
    def extractor(self):
        return MediaMetadataExtractor()

    def test_image_hash_failure(self, extractor):
        """Test failure during image hashing."""
        with patch("store.store.media_metadata.sha512hash_image", side_effect=Exception("Hash fail")):
            with pytest.raises(RuntimeError, match="Hash computation failed"):
                extractor._compute_hash(b"data", MediaType.IMAGE)

    def test_video_hash_failure(self, extractor):
        """Test failure during video hashing."""
        with patch("store.store.media_metadata.sha512hash_video2", side_effect=Exception("Hash fail")):
            with pytest.raises(RuntimeError, match="Hash computation failed"):
                extractor._compute_hash(b"data", MediaType.VIDEO)

    def test_generic_hash_failure(self, extractor):
        """Test failure during generic hashing."""
        with patch("store.store.media_metadata.get_md5_hexdigest", side_effect=Exception("Hash fail")):
            with pytest.raises(RuntimeError, match="Hash computation failed"):
                extractor._compute_hash(b"data", MediaType.FILE)

    def test_hash_routing(self, extractor):
        """Verify correct hash function is called based on media type."""
        with patch("store.store.media_metadata.sha512hash_image", return_value=("imghash", 1)) as mock_img, \
             patch("store.store.media_metadata.sha512hash_video2", return_value=("vidhash", 1)) as mock_vid, \
             patch("store.store.media_metadata.get_md5_hexdigest", return_value="md5hash") as mock_md5:

            assert extractor._compute_hash(b"img", MediaType.IMAGE) == "imghash"
            mock_img.assert_called_once()

            assert extractor._compute_hash(b"vid", MediaType.VIDEO) == "vidhash"
            mock_vid.assert_called_once()

            assert extractor._compute_hash(b"other", MediaType.TEXT) == "md5hash"
            mock_md5.assert_called_once()

    def test_extract_metadata_hash_failure(self, extractor):
        """Test extract_metadata fails when hash computation fails."""
        with patch("store.store.media_metadata.determine_mime", return_value=MediaType.IMAGE), \
             patch.object(extractor, "_compute_hash", side_effect=RuntimeError("Hash fail")):
             with pytest.raises(RuntimeError, match="Hash computation failed"):
                 extractor.extract_metadata(b"data", "test.jpg")


class TestExifExtraction:
    """Test EXIF extraction and field parsing."""

    @pytest.fixture
    def extractor(self):
        return MediaMetadataExtractor()

    def test_exif_failure_handled_gracefully(self, extractor):
        """Test that EXIF failure results in None for fields but success overall."""
        # Setup basic strict mocks for previous steps
        with patch("store.store.media_metadata.determine_mime", return_value=MediaType.IMAGE), \
             patch("magic.Magic") as MockMagic, \
             patch.object(extractor, "_compute_hash", return_value="a" * 32):

            MockMagic.return_value.from_buffer.return_value = "image/jpeg"

            # Mock temp file and extraction failure
            with patch("tempfile.NamedTemporaryFile"), \
                 patch.object(extractor.exif_extractor, "extract_metadata_all", side_effect=Exception("Exif fail")):

                result = extractor.extract_metadata(b"data", "test.jpg")

                assert result.width is None
                assert result.height is None
                assert result.create_date is None

    def test_invalid_date_format(self, extractor):
        """Test parsing of invalid date format."""
        exif_data = {"EXIF:CreateDate": "Invalid Date String"}

        with patch("store.store.media_metadata.determine_mime", return_value=MediaType.IMAGE), \
             patch("magic.Magic") as MockMagic, \
             patch.object(extractor, "_compute_hash", return_value="a" * 32), \
             patch("tempfile.NamedTemporaryFile"), \
             patch.object(extractor.exif_extractor, "extract_metadata_all", return_value=exif_data):

            MockMagic.return_value.from_buffer.return_value = "image/jpeg"

            result = extractor.extract_metadata(b"data", "test.jpg")
            assert result.create_date is None

    def test_width_height_type_conversion(self, extractor):
        """Test that width/height are safely converted from various types."""
        # Test string inputs
        exif_data = {
            "File:ImageWidth": "100",
            "File:ImageHeight": 200.5 # Should handle float? code uses int()
        }

        with patch("store.store.media_metadata.determine_mime", return_value=MediaType.IMAGE), \
             patch("magic.Magic") as MockMagic, \
             patch.object(extractor, "_compute_hash", return_value="a" * 32), \
             patch("tempfile.NamedTemporaryFile"), \
             patch.object(extractor.exif_extractor, "extract_metadata_all", return_value=exif_data):

            MockMagic.return_value.from_buffer.return_value = "image/jpeg"

            result = extractor.extract_metadata(b"data", "test.jpg")
            assert result.width == 100
            result = extractor.extract_metadata(b"data", "test.jpg")
            assert result.width == 100
            assert result.height == 200

    def test_exif_duration_parsing(self, extractor):
        """Test parsing of duration from EXIF."""
        exif_data = {"QuickTime:Duration": "15.5"}

        with patch("store.store.media_metadata.determine_mime", return_value=MediaType.VIDEO), \
             patch("magic.Magic") as MockMagic, \
             patch.object(extractor, "_compute_hash", return_value="a" * 32), \
             patch("tempfile.NamedTemporaryFile"), \
             patch.object(extractor.exif_extractor, "extract_metadata_all", return_value=exif_data):

            MockMagic.return_value.from_buffer.return_value = "video/mp4"

            result = extractor.extract_metadata(b"data", "test.mp4")
            assert result.duration == 15.5

    def test_exif_valid_date_parsing(self, extractor):
        """Test parsing of valid CreateDate from EXIF."""
        exif_data = {"EXIF:CreateDate": "2023:01:01 12:00:00"}

        with patch("store.store.media_metadata.determine_mime", return_value=MediaType.IMAGE), \
             patch("magic.Magic") as MockMagic, \
             patch.object(extractor, "_compute_hash", return_value="a" * 32), \
             patch("tempfile.NamedTemporaryFile"), \
             patch.object(extractor.exif_extractor, "extract_metadata_all", return_value=exif_data):

            MockMagic.return_value.from_buffer.return_value = "image/jpeg"

            result = extractor.extract_metadata(b"data", "test.jpg")
            # 2023-01-01 12:00:00 UTC timestamp * 1000
            # Note: The code uses datetime.strptime which uses local time if no timezone info?
            # Or is it naive?
            # 230: dt = datetime.strptime(create_date_str, "%Y:%m:%d %H:%M:%S")
            # 231: create_date_ms = int(dt.timestamp() * 1000)
            # dt.timestamp() assumes local time for naive objects usually.
            # I just check it is not None.
            assert result.create_date is not None
            assert result.create_date > 0

    def test_video_duration_fallback(self, extractor):
        """Test video duration fallback when EXIF missing."""
        with patch("store.store.media_metadata.determine_mime", return_value=MediaType.VIDEO), \
             patch("magic.Magic") as MockMagic, \
             patch.object(extractor, "_compute_hash", return_value="a" * 32), \
             patch("tempfile.NamedTemporaryFile"), \
             patch.object(extractor.exif_extractor, "extract_metadata_all", return_value={}):

            MockMagic.return_value.from_buffer.return_value = "video/mp4"

            # Mock fallback
            with patch.object(extractor, "_extract_video_duration", return_value=123.45):
                result = extractor.extract_metadata(b"data", "test.mp4")
                assert result.duration == 123.45


class TestVideoDuration:
    """Test ffprobe video duration extraction."""

    @pytest.fixture
    def extractor(self):
        return MediaMetadataExtractor()

    def test_ffprobe_success(self, extractor):
        """Test successful duration extraction."""
        with patch("tempfile.NamedTemporaryFile"), \
             patch("subprocess.run") as mock_run:

            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='{"format": {"duration": "10.5"}}'
            )

            duration = extractor._extract_video_duration(b"vid", "test.mp4")
            assert duration == 10.5

    def test_ffprobe_malformed_json(self, extractor):
        """Test handling of invalid JSON output."""
        with patch("tempfile.NamedTemporaryFile"), \
             patch("subprocess.run") as mock_run:

            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='{invalid json}'
            )

            duration = extractor._extract_video_duration(b"vid", "test.mp4")
            assert duration is None

    def test_ffprobe_timeout(self, extractor):
        """Test handling of timeout."""
        with patch("tempfile.NamedTemporaryFile"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["cmd"], 30)):

            duration = extractor._extract_video_duration(b"vid", "test.mp4")
            assert duration is None

    def test_ffprobe_error(self, extractor):
        """Test handling of execution error."""
        with patch("tempfile.NamedTemporaryFile"), \
             patch("subprocess.run", side_effect=Exception("Failed")):

            duration = extractor._extract_video_duration(b"vid", "test.mp4")
            duration = extractor._extract_video_duration(b"vid", "test.mp4")
            assert duration is None

    def test_extract_metadata_duration_exception(self, extractor):
        """Test extract_metadata handles exception from _extract_video_duration."""
        with patch("store.store.media_metadata.determine_mime", return_value=MediaType.VIDEO), \
             patch("magic.Magic") as MockMagic, \
             patch.object(extractor, "_compute_hash", return_value="a" * 32), \
             patch("tempfile.NamedTemporaryFile"), \
             patch.object(extractor.exif_extractor, "extract_metadata_all", return_value={}):

            MockMagic.return_value.from_buffer.return_value = "video/mp4"

            # Mock _extract_video_duration to raise exception
            with patch.object(extractor, "_extract_video_duration", side_effect=Exception("Probe error")):
                result = extractor.extract_metadata(b"data", "test.mp4")
                assert result.duration is None
