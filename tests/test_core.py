"""Tests for LibertyJog core functionality."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from libertyjog.core import LibertyJogProcessor


class TestLibertyJogProcessor:
    """Test cases for the LibertyJogProcessor class."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.processor = LibertyJogProcessor()

    def test_init(self) -> None:
        """Test processor initialization."""
        assert self.processor.m3_pattern is not None
        assert self.processor.positioning_heights == []
        assert self.processor.modifications_made == 0

    def test_validate_sbp_file_valid(self) -> None:
        """Test validation with a valid .sbp file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sbp", delete=False) as f:
            f.write("' Test ShopBot file\n")
            f.write("SA\n")
            f.write("M3, 1.0, 2.0, 3.0\n")
            temp_path = Path(f.name)

        try:
            assert self.processor.validate_sbp_file(temp_path) is True
        finally:
            temp_path.unlink()

    def test_validate_sbp_file_invalid_extension(self) -> None:
        """Test validation with invalid file extension."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("SA\nM3, 1.0, 2.0, 3.0\n")
            temp_path = Path(f.name)

        try:
            assert self.processor.validate_sbp_file(temp_path) is False
        finally:
            temp_path.unlink()

    def test_validate_sbp_file_nonexistent(self) -> None:
        """Test validation with non-existent file."""
        assert self.processor.validate_sbp_file(Path("nonexistent.sbp")) is False

    def test_validate_sbp_file_no_shopbot_commands(self) -> None:
        """Test validation with .sbp file that doesn't contain ShopBot commands."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sbp", delete=False) as f:
            f.write("This is just text\n")
            f.write("No ShopBot commands here\n")
            temp_path = Path(f.name)

        try:
            assert self.processor.validate_sbp_file(temp_path) is False
        finally:
            temp_path.unlink()

    def test_analyze_file_nonexistent(self) -> None:
        """Test analysis of non-existent file."""
        with pytest.raises(FileNotFoundError):
            self.processor.analyze_file(Path("nonexistent.sbp"))

    def test_analyze_file_wrong_extension(self) -> None:
        """Test analysis of file with wrong extension."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("M3, 1.0, 2.0, 3.0\n")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match=r"File must have \.sbp extension"):
                self.processor.analyze_file(temp_path)
        finally:
            temp_path.unlink()

    def test_analyze_file_no_m3_commands(self) -> None:
        """Test analysis of file with no M3 commands."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sbp", delete=False) as f:
            f.write("' Test file\n")
            f.write("SA\n")
            f.write("CN, 90\n")
            temp_path = Path(f.name)

        try:
            result = self.processor.analyze_file(temp_path)
            assert result["error"] == "No M3 commands found in file"
            assert result["m3_commands"] == 0
            assert result["total_lines"] == 3
        finally:
            temp_path.unlink()

    def test_analyze_file_with_m3_commands(self) -> None:
        """Test analysis of file with M3 commands."""
        content = [
            "' Test file",
            "SA",
            "M3, 1.0, 2.0, 0.5906",  # Retract height
            "M3, 1.1, 2.1, -0.1",  # Cutting
            "M3, 1.2, 2.2, 0.5906",  # Retract height again
            "M3, 1.3, 2.3, -0.2",  # Cutting
            "M3, 1.4, 2.4, 0.5906",  # Retract height again
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sbp", delete=False) as f:
            f.write("\n".join(content))
            temp_path = Path(f.name)

        try:
            result = self.processor.analyze_file(temp_path)
            assert "error" not in result
            assert result["m3_commands"] == 5
            assert result["total_lines"] == 7
            assert result["max_z"] == 0.5906
            assert result["suggested_retract_height"] == 0.5906
            # Should have 3 occurrences of 0.5906
            assert result["z_counter"][0.5906] == 3
        finally:
            temp_path.unlink()

    def test_process_file_basic(self) -> None:
        """Test basic file processing."""
        content = [
            "' Original file",
            "SA",
            "M3, 1.0, 2.0, 0.5906",  # Should be converted
            "M3, 1.1, 2.1, -0.1",  # Should not be converted
            "M3, 1.2, 2.2, 0.5906",  # Should be converted
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sbp", delete=False) as input_f:
            input_f.write("\n".join(content))
            input_path = Path(input_f.name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sbp", delete=False) as output_f:
            output_path = Path(output_f.name)

        try:
            result = self.processor.process_file(input_path=input_path, output_path=output_path, retract_height=0.5906)

            assert result["success"] is True
            assert result["modifications_made"] == 2
            assert result["retract_height"] == 0.5906

            # Check that no backup was created (custom output path)
            assert "backup_file" not in result
            assert result["in_place_modification"] is False

            # Check output file content
            with open(output_path) as f:
                output_content = f.read()

            assert "LibertyJog" in output_content
            assert "Feed height detected as: 0.5906" in output_content
            assert "J3, 1.0, 2.0, 0.5906" in output_content
            assert "J3, 1.2, 2.2, 0.5906" in output_content
            assert "M3, 1.1, 2.1, -0.1" in output_content  # Should remain M3

        finally:
            input_path.unlink()
            output_path.unlink()

    def test_process_file_in_place_modification(self) -> None:
        """Test processing with in-place modification (default behavior)."""
        content = ["M3, 1.0, 2.0, 0.5906"]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sbp", delete=False) as input_f:
            input_f.write("\n".join(content))
            input_path = Path(input_f.name)

        try:
            result = self.processor.process_file(input_path=input_path, retract_height=0.5906)

            # Should modify the input file in-place
            assert result["output_file"] == str(input_path)
            assert result["in_place_modification"] is True

            # Check backup was created
            assert "backup_file" in result
            backup_path = Path(result["backup_file"])
            assert backup_path.exists()

            # Verify backup contains original content
            with open(backup_path) as f:
                backup_content = f.read()
            assert backup_content == "\n".join(content)

            # Verify input file was modified
            with open(input_path) as f:
                modified_content = f.read()
            assert "J3, 1.0, 2.0, 0.5906" in modified_content

            # Clean up backup file
            backup_path.unlink()

        finally:
            input_path.unlink()

    def test_process_file_with_analysis_error(self) -> None:
        """Test processing file that has analysis errors."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sbp", delete=False) as f:
            f.write("' No M3 commands\nSA\n")
            temp_path = Path(f.name)

        try:
            result = self.processor.process_file(temp_path, retract_height=1.0)
            assert "error" in result
            assert result["error"] == "No M3 commands found in file"
        finally:
            temp_path.unlink()

    @patch("libertyjog.core.LibertyJogProcessor._get_version")
    def test_get_version_with_import(self, mock_get_version) -> None:
        """Test version retrieval."""
        mock_get_version.return_value = "0.1.0"
        version = self.processor._get_version()
        assert version == "0.1.0"

    def test_backup_creation(self) -> None:
        """Test that backup files are created with proper naming and content."""
        content = ["' Original file", "SA", "M3, 1.0, 2.0, 0.5906"]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sbp", delete=False) as input_f:
            input_f.write("\n".join(content))
            input_path = Path(input_f.name)

        try:
            result = self.processor.process_file(input_path=input_path, retract_height=0.5906)

            assert result["success"] is True
            assert "backup_file" in result

            backup_path = Path(result["backup_file"])

            # Check backup file properties
            assert backup_path.exists()
            assert backup_path.name.endswith(".backup")
            assert input_path.name in backup_path.name
            assert backup_path.parent == input_path.parent

            # Check backup contains original content exactly
            with open(backup_path) as f:
                backup_content = f.read()
            assert backup_content == "\n".join(content)

            # Check backup filename format (should have timestamp)
            import re

            expected_pattern = rf"{re.escape(input_path.name)}\.(\d{{8}}_\d{{6}})\.backup"
            assert re.match(expected_pattern, backup_path.name)

        finally:
            input_path.unlink()
            if "result" in locals() and "backup_file" in result:
                Path(result["backup_file"]).unlink(missing_ok=True)
            # Clean up auto-generated output file
            output_path = input_path.parent / f"{input_path.stem}_libertyjog.sbp"
            output_path.unlink(missing_ok=True)

    def test_backup_creation_failure(self) -> None:
        """Test handling of backup creation failure."""
        content = ["M3, 1.0, 2.0, 0.5906"]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sbp", delete=False) as input_f:
            input_f.write("\n".join(content))
            input_path = Path(input_f.name)

        # Make the directory read-only to cause backup failure
        original_permissions = input_path.parent.stat().st_mode

        try:
            # Make parent directory read-only (on systems that support it)
            try:
                input_path.parent.chmod(0o555)

                result = self.processor.process_file(input_path=input_path, retract_height=0.5906)

                # Should return error about backup failure
                assert "error" in result
                assert "Failed to create backup" in result["error"]

            except (PermissionError, OSError):
                # If we can't change permissions (e.g., on some CI systems), skip this test
                pytest.skip("Cannot change directory permissions on this system")

        finally:
            # Restore permissions
            try:
                input_path.parent.chmod(original_permissions)
            except (PermissionError, OSError):
                pass
            input_path.unlink(missing_ok=True)

    def test_speed_detection_from_file(self) -> None:
        """Test that MS and JS commands are properly detected and used."""
        content = [
            "' Test file with speed commands",
            "SA",
            "MS, 1.5, 1.0",  # Move speed: 1.5 in/sec XY, 1.0 in/sec Z
            "JS, 5.0, 2.0",  # Jog speed: 5.0 in/sec XY, 2.0 in/sec Z
            "M3, 1.0, 2.0, 0.5906",
            "M3, 1.1, 2.1, -0.1",
            "M3, 1.2, 2.2, 0.5906",
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sbp", delete=False) as input_f:
            input_f.write("\n".join(content))
            input_path = Path(input_f.name)

        try:
            analysis = self.processor.analyze_file(input_path)

            # Check that speeds were detected from file
            assert analysis["detected_move_speed"] == 90.0  # 1.5 * 60 = 90 IPM
            assert analysis["detected_jog_speed"] == 300.0  # 5.0 * 60 = 300 IPM
            assert analysis["actual_cutting_speed"] == 90.0
            assert analysis["actual_jog_speed"] == 300.0

        finally:
            input_path.unlink()

    def test_speed_fallback_to_defaults(self) -> None:
        """Test that configured defaults are used when no MS/JS commands found."""
        content = [
            "' Test file without speed commands",
            "SA",
            "M3, 1.0, 2.0, 0.5906",
            "M3, 1.1, 2.1, -0.1",
            "M3, 1.2, 2.2, 0.5906",
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sbp", delete=False) as input_f:
            input_f.write("\n".join(content))
            input_path = Path(input_f.name)

        try:
            # Set custom defaults
            self.processor.cutting_speed_ipm = 45.0
            self.processor.jog_speed_ipm = 250.0

            analysis = self.processor.analyze_file(input_path)

            # Check that no speeds were detected from file
            assert analysis["detected_move_speed"] is None
            assert analysis["detected_jog_speed"] is None
            # Check that configured defaults were used
            assert analysis["actual_cutting_speed"] == 45.0
            assert analysis["actual_jog_speed"] == 250.0

        finally:
            input_path.unlink()


class TestRealArtifacts:
    """Test with real artifact files."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.processor = LibertyJogProcessor()
        self.artifacts_dir = Path(__file__).parent.parent / "artifacts"

    def test_analyze_real_roughing_pass(self) -> None:
        """Test analysis of real roughing pass file."""
        file_path = self.artifacts_dir / "1001 roughing pass.sbp"
        if not file_path.exists():
            pytest.skip("Real artifact file not found")

        result = self.processor.analyze_file(file_path)

        assert "error" not in result
        assert result["m3_commands"] > 0
        assert result["total_lines"] > 0
        assert result["suggested_retract_height"] is not None
        assert result["max_z"] > 0

    def test_analyze_real_bevel_file(self) -> None:
        """Test analysis of real bevel file."""
        file_path = self.artifacts_dir / "1001-bevel.sbp"
        if not file_path.exists():
            pytest.skip("Real artifact file not found")

        result = self.processor.analyze_file(file_path)

        assert "error" not in result
        assert result["m3_commands"] > 0

    def test_process_real_drill_file(self) -> None:
        """Test processing of real drill file."""
        file_path = self.artifacts_dir / "1003-drill.sbp"
        if not file_path.exists():
            pytest.skip("Real artifact file not found")

        # First analyze to get suggested retract height
        analysis = self.processor.analyze_file(file_path)
        if "error" in analysis:
            pytest.skip("Analysis failed on real file")

        retract_height = analysis["suggested_retract_height"]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sbp", delete=False) as output_f:
            output_path = Path(output_f.name)

        try:
            result = self.processor.process_file(
                input_path=file_path, output_path=output_path, positioning_heights=[retract_height]
            )

            assert result["success"] is True
            assert result["retract_height"] == retract_height

            # Check that no backup was created (custom output path)
            assert "backup_file" not in result
            assert result["in_place_modification"] is False

            # Verify output file exists and has content
            assert output_path.exists()
            assert output_path.stat().st_size > 0

            # Check that it has the header
            with open(output_path) as f:
                first_lines = f.read(200)
                assert "LibertyJog" in first_lines

        finally:
            if output_path.exists():
                output_path.unlink()

    def test_validate_real_artifacts(self) -> None:
        """Test validation of real artifact files."""
        if not self.artifacts_dir.exists():
            pytest.skip("Artifacts directory not found")

        sbp_files = list(self.artifacts_dir.glob("*.sbp"))
        if not sbp_files:
            pytest.skip("No .sbp files found in artifacts")

        for sbp_file in sbp_files:
            assert self.processor.validate_sbp_file(sbp_file), f"Failed to validate {sbp_file}"
