"""Tests for ShopBotJog CLI interface."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from shopbotjog.cli import main


class TestCLI:
    """Test cases for the CLI interface."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def create_test_sbp_file(self, content: list[str]) -> Path:
        """Create a temporary .sbp file with given content."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sbp", delete=False) as f:
            f.write("\n".join(content))
            return Path(f.name)

    def test_cli_help(self) -> None:
        """Test CLI help message."""
        result = self.runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "ShopBotJog" in result.output
        assert "INPUT_FILE" in result.output

    def test_cli_nonexistent_file(self) -> None:
        """Test CLI with non-existent file."""
        result = self.runner.invoke(main, ["nonexistent.sbp"])
        assert result.exit_code != 0

    def test_cli_invalid_file(self) -> None:
        """Test CLI with invalid .sbp file."""
        content = ["This is not a valid ShopBot file", "No commands here"]
        temp_file = self.create_test_sbp_file(content)

        try:
            result = self.runner.invoke(main, [str(temp_file), "--yes", "--quiet"])
            assert result.exit_code != 0
            assert "Invalid .sbp file" in result.output
        finally:
            temp_file.unlink()

    def test_cli_analyze_only(self) -> None:
        """Test CLI analyze-only mode."""
        content = ["' Test file", "SA", "M3, 1.0, 2.0, 0.5906", "M3, 1.1, 2.1, -0.1", "M3, 1.2, 2.2, 0.5906"]
        temp_file = self.create_test_sbp_file(content)

        try:
            result = self.runner.invoke(main, [str(temp_file), "--analyze-only", "--quiet"])
            assert result.exit_code == 0
            assert "Analysis complete" in result.output
            assert "Use without --analyze-only" in result.output
        finally:
            temp_file.unlink()

    def test_cli_process_with_yes_flag(self) -> None:
        """Test CLI processing with --yes flag (in-place modification)."""
        content = ["' Test file", "SA", "M3, 1.0, 2.0, 0.5906", "M3, 1.1, 2.1, -0.1", "M3, 1.2, 2.2, 0.5906"]
        temp_file = self.create_test_sbp_file(content)

        try:
            result = self.runner.invoke(main, [str(temp_file), "--yes", "--quiet"])
            assert result.exit_code == 0
            assert "Successfully processed" in result.output
            assert "Backup created:" in result.output
            assert "Modified file in-place:" in result.output

            # Check that original file was modified with J3 commands
            with open(temp_file) as f:
                modified_content = f.read()
                assert "J3, 1.0, 2.0, 0.5906" in modified_content
                assert "J3, 1.2, 2.2, 0.5906" in modified_content

        finally:
            temp_file.unlink()
            # Clean up any backup files
            for backup in temp_file.parent.glob(f"{temp_file.name}.*.backup"):
                backup.unlink()

    def test_cli_process_with_manual_feed_height(self) -> None:
        """Test CLI processing with manually specified --feed-height option."""
        content = [
            "' Test file",
            "SA",
            "M3, 1.0, 2.0, 1.5",  # This will be the manual feed height
            "M3, 1.1, 2.1, -0.1",
            "M3, 1.2, 2.2, 1.5",
        ]
        temp_file = self.create_test_sbp_file(content)

        try:
            result = self.runner.invoke(main, [str(temp_file), "--feed-height", "1.5", "--yes", "--quiet"])
            assert result.exit_code == 0
            assert "Successfully processed" in result.output

            # Check that the manually specified feed height was used
            with open(temp_file) as f:
                output_content = f.read()
                assert "Feed height detected as: 1.5" in output_content
                assert "J3, 1.0, 2.0, 1.5" in output_content

        finally:
            temp_file.unlink()
            # Clean up any backup files
            for backup in temp_file.parent.glob(f"{temp_file.name}.*.backup"):
                backup.unlink()

    def test_cli_process_with_negative_z_safety(self) -> None:
        """Test CLI processing excludes negative Z values as expected."""
        content = [
            "' Test file",
            "SA",
            "M3, 1.0, 2.0, 0.19",  # Positive Z - should be detected
            "M3, 1.1, 2.1, -0.1",  # Negative Z - should be excluded
            "M3, 1.2, 2.2, 0.19",  # Positive Z - should be detected
            "M3, 1.3, 2.3, -0.5",  # Negative Z - should be excluded
        ]
        temp_file = self.create_test_sbp_file(content)

        try:
            result = self.runner.invoke(main, [str(temp_file), "--yes", "--quiet"])
            assert result.exit_code == 0
            assert "Successfully processed" in result.output

            # Check that only positive Z heights were converted
            with open(temp_file) as f:
                output_content = f.read()
                assert "J3, 1.0, 2.0, 0.19" in output_content  # Converted
                assert "J3, 1.2, 2.2, 0.19" in output_content  # Converted
                assert "M3, 1.1, 2.1, -0.1" in output_content  # Not converted (negative)
                assert "M3, 1.3, 2.3, -0.5" in output_content  # Not converted (negative)

        finally:
            temp_file.unlink()
            # Clean up any backup files
            for backup in temp_file.parent.glob(f"{temp_file.name}.*.backup"):
                backup.unlink()

    def test_cli_process_with_custom_output(self) -> None:
        """Test CLI processing with custom output file."""
        content = ["' Test file", "SA", "M3, 1.0, 2.0, 0.5906"]
        temp_file = self.create_test_sbp_file(content)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sbp", delete=False) as output_f:
            output_file = Path(output_f.name)

        try:
            result = self.runner.invoke(
                main, [str(temp_file), "--output", str(output_file), "--feed-height", "0.5906", "--yes", "--quiet"]
            )
            assert result.exit_code == 0
            assert str(output_file) in result.output
            assert output_file.exists()

        finally:
            temp_file.unlink()
            if output_file.exists():
                output_file.unlink()
            # Clean up any backup files
            for backup in temp_file.parent.glob(f"{temp_file.name}.*.backup"):
                backup.unlink()

    def test_cli_no_m3_commands(self) -> None:
        """Test CLI with file that has no M3 commands."""
        content = ["' Test file with no M3 commands", "SA", "CN, 90", "TR, 12000"]
        temp_file = self.create_test_sbp_file(content)

        try:
            result = self.runner.invoke(main, [str(temp_file), "--yes", "--quiet"])
            assert result.exit_code != 0
            assert "No M3 commands found" in result.output
        finally:
            temp_file.unlink()

    @patch("shopbotjog.cli.Confirm.ask")
    def test_cli_user_confirms_retract_height(self, mock_confirm) -> None:
        """Test CLI when user confirms detected retract height."""
        mock_confirm.return_value = True

        content = [
            "' Test file",
            "SA",
            "M3, 1.0, 2.0, 0.5906",
            "M3, 1.0, 2.0, 0.5906",  # Multiple occurrences to trigger detection
            "M3, 1.1, 2.1, -0.1",
        ]
        temp_file = self.create_test_sbp_file(content)

        try:
            result = self.runner.invoke(main, [str(temp_file), "--quiet"])
            assert result.exit_code == 0
            mock_confirm.assert_called_once()
        finally:
            temp_file.unlink()
            # Clean up any backup files
            for backup in temp_file.parent.glob(f"{temp_file.name}.*.backup"):
                backup.unlink()

    @patch("shopbotjog.cli.FloatPrompt.ask")
    @patch("shopbotjog.cli.Confirm.ask")
    def test_cli_user_rejects_retract_height(self, mock_confirm, mock_prompt) -> None:
        """Test CLI when user rejects detected retract height."""
        mock_confirm.return_value = False
        mock_prompt.return_value = 1.0

        content = [
            "' Test file",
            "SA",
            "M3, 1.0, 2.0, 0.5906",
            "M3, 1.0, 2.0, 0.5906",  # Multiple occurrences to trigger detection
            "M3, 1.1, 2.1, 1.0",
            "M3, 1.1, 2.1, 1.0",  # User will specify 1.0 as retract height
        ]
        temp_file = self.create_test_sbp_file(content)

        try:
            result = self.runner.invoke(main, [str(temp_file), "--quiet"])
            assert result.exit_code == 0
            mock_confirm.assert_called_once()
            mock_prompt.assert_called_once()

            # Check that the user-specified retract height was used
            with open(temp_file) as f:
                output_content = f.read()
                assert "Feed height detected as: 1.0" in output_content

        finally:
            temp_file.unlink()
            # Clean up any backup files
            for backup in temp_file.parent.glob(f"{temp_file.name}.*.backup"):
                backup.unlink()

    def test_cli_keyboard_interrupt(self) -> None:
        """Test CLI handling of keyboard interrupt."""
        content = ["SA", "M3, 1.0, 2.0, 0.5906"]
        temp_file = self.create_test_sbp_file(content)

        try:
            # Simulate KeyboardInterrupt during processing
            with patch("shopbotjog.cli.console.print") as mock_print:
                mock_print.side_effect = KeyboardInterrupt()
                result = self.runner.invoke(main, [str(temp_file), "--yes", "--quiet"])
                assert result.exit_code != 0
        finally:
            temp_file.unlink()

    def test_cli_speed_detection_display(self) -> None:
        """Test CLI displays correct speed sources in analysis."""
        content = [
            "' Test file with speed commands",
            "SA",
            "MS, 2.0, 1.0",  # Move speed: 2.0 in/sec = 120 IPM
            "JS, 4.0, 2.0",  # Jog speed: 4.0 in/sec = 240 IPM
            "M3, 1.0, 2.0, 0.5906",
            "M3, 1.1, 2.1, 0.5906",
        ]
        temp_file = self.create_test_sbp_file(content)

        try:
            result = self.runner.invoke(main, [str(temp_file), "--analyze-only"])
            assert result.exit_code == 0

            # Check that speeds are shown as detected from file commands
            assert "120.0 IPM (from MS command)" in result.output
            assert "240.0 IPM (from JS command)" in result.output
        finally:
            temp_file.unlink()

    def test_cli_speed_fallback_display(self) -> None:
        """Test CLI displays fallback defaults when no speed commands found."""
        content = ["' Test file without speed commands", "SA", "M3, 1.0, 2.0, 0.5906", "M3, 1.1, 2.1, 0.5906"]
        temp_file = self.create_test_sbp_file(content)

        try:
            result = self.runner.invoke(
                main, [str(temp_file), "--analyze-only", "--cutting-speed", "75", "--jog-speed", "350"]
            )
            assert result.exit_code == 0

            # Check that speeds are shown as fallback defaults
            assert "75.0 IPM (fallback default)" in result.output
            assert "350.0 IPM (fallback default)" in result.output
        finally:
            temp_file.unlink()

    def test_cli_invalid_manual_feed_height_fails(self) -> None:
        """Test CLI fails when manually specified feed height doesn't exist."""
        content = ["' Test file", "SA", "M3, 1.0, 2.0, 0.5906", "M3, 1.1, 2.1, 0.5906"]
        temp_file = self.create_test_sbp_file(content)

        try:
            result = self.runner.invoke(
                main,
                [
                    str(temp_file),
                    "--feed-height",
                    "99.9999",  # Non-existent height
                    "--yes",
                ],
            )
            assert result.exit_code != 0
            assert "Error: Manually specified feed height 99.9999 not found in file" in result.output
            assert "Available positive heights in file:" in result.output
            assert "0.5906 (2 occurrences)" in result.output

            # Verify original file was not modified (since operation failed)
            with open(temp_file) as f:
                content_after = f.read()
                # Should contain original M3 commands (not converted to J3)
                assert "M3, 1.0, 2.0, 0.5906" in content_after
                assert "J3," not in content_after

        finally:
            temp_file.unlink()
            # Clean up any backup files (there shouldn't be any since processing failed)
            for backup in temp_file.parent.glob(f"{temp_file.name}.*.backup"):
                backup.unlink()

    def test_cli_manual_feed_height_skips_confirmation(self) -> None:
        """Test that manually specifying feed height skips confirmation prompts."""
        content = ["' Test file", "SA", "M3, 1.0, 2.0, 0.5906", "M3, 1.1, 2.1, 0.5906"]
        temp_file = self.create_test_sbp_file(content)

        try:
            result = self.runner.invoke(
                main,
                [
                    str(temp_file),
                    "--feed-height",
                    "0.5906",  # Valid height
                    "--quiet",
                ],
            )
            assert result.exit_code == 0

            # Should not contain confirmation prompts
            assert "Proceed with these height conversions?" not in result.output
            assert "Please enter the feed height" not in result.output

            # Should process successfully
            assert "Successfully processed" in result.output

        finally:
            temp_file.unlink()
            # Clean up any backup files
            for backup in temp_file.parent.glob(f"{temp_file.name}.*.backup"):
                backup.unlink()


class TestCLIWithRealArtifacts:
    """Test CLI with real artifact files."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.artifacts_dir = Path(__file__).parent.parent / "artifacts"

    def test_cli_analyze_real_file(self) -> None:
        """Test CLI analysis of real artifact file."""
        file_path = self.artifacts_dir / "1003-drill.sbp"
        if not file_path.exists():
            pytest.skip("Real artifact file not found")

        result = self.runner.invoke(main, [str(file_path), "--analyze-only", "--quiet"])
        assert result.exit_code == 0
        assert "Analysis complete" in result.output

    def test_cli_process_real_file_dry_run(self) -> None:
        """Test CLI processing of real file without actually modifying."""
        file_path = self.artifacts_dir / "1001 roughing pass.sbp"
        if not file_path.exists():
            pytest.skip("Real artifact file not found")

        # Just run analysis to make sure it doesn't crash
        result = self.runner.invoke(main, [str(file_path), "--analyze-only"])
        assert result.exit_code == 0
