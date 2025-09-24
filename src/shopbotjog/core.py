"""Core ShopBotJog processing functionality."""

import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


class ShopBotJogProcessor:
    """Processes ShopBot .sbp files to optimize rapid movements."""

    def __init__(self) -> None:
        """Initialize the processor."""
        self.m3_pattern = re.compile(r"^M3,\s*([\d.-]+),\s*([\d.-]+),\s*([\d.-]+)$")
        self.ms_pattern = re.compile(r"^MS,\s*([\d.-]+)(?:,\s*([\d.-]+))?")  # Move Speed command
        self.js_pattern = re.compile(r"^JS,\s*([\d.-]+)(?:,\s*([\d.-]+))?")  # Jog Speed command
        self.positioning_heights: list[float] = []
        self.modifications_made = 0

        # Default speed assumptions (can be overridden)
        self.cutting_speed_ipm = 60.0  # Default cutting feedrate
        self.jog_speed_ipm = 300.0  # Default jog speed

    def analyze_file(self, file_path: Path) -> dict[str, Any]:
        """Analyze a .sbp file to find M3 commands and potential retract height.

        Args:
            file_path: Path to the .sbp file

        Returns:
            Dictionary containing analysis results
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if file_path.suffix.lower() != ".sbp":
            raise ValueError(f"File must have .sbp extension: {file_path}")

        z_values: list[float] = []
        m3_coordinates: list[tuple[float, float, float]] = []  # (x, y, z) coordinates
        m3_commands = 0
        total_lines = 0

        # Speed detection from file
        detected_move_speed = None
        detected_jog_speed = None

        with open(file_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                total_lines += 1
                line = line.strip()

                # Check for M3 commands
                match = self.m3_pattern.match(line)
                if match:
                    m3_commands += 1
                    x, y, z = match.groups()
                    z_values.append(float(z))
                    m3_coordinates.append((float(x), float(y), float(z)))
                    continue

                # Check for Move Speed (MS) commands - speeds are in inches/second
                match = self.ms_pattern.match(line)
                if match:
                    xy_speed, _z_speed = match.groups()
                    # Convert from inches/second to inches/minute for consistency
                    detected_move_speed = float(xy_speed) * 60
                    continue

                # Check for Jog Speed (JS) commands - speeds are in inches/second
                match = self.js_pattern.match(line)
                if match:
                    xy_speed, _z_speed = match.groups()
                    # Convert from inches/second to inches/minute for consistency
                    detected_jog_speed = float(xy_speed) * 60
                    continue

        if not z_values:
            return {
                "error": "No M3 commands found in file",
                "total_lines": total_lines,
                "m3_commands": 0,
                "z_values": [],
                "suggested_retract_height": None,
            }

        # Use detected speeds if available, otherwise use configured defaults
        actual_cutting_speed = detected_move_speed if detected_move_speed is not None else self.cutting_speed_ipm
        actual_jog_speed = detected_jog_speed if detected_jog_speed is not None else self.jog_speed_ipm

        # Analyze positioning heights (retract and clearance)
        positioning_analysis = self._analyze_positioning_heights(z_values)

        return {
            "total_lines": total_lines,
            "m3_commands": m3_commands,
            "z_values": z_values,
            "z_counter": positioning_analysis["z_counter"],
            "max_z": positioning_analysis["max_z"],
            "min_z": positioning_analysis["min_z"],
            "positioning_heights": positioning_analysis["positioning_heights"],
            "clearance_height": positioning_analysis.get("clearance_height"),
            "retract_height": positioning_analysis.get("retract_height"),
            "feed_height": positioning_analysis.get("feed_height"),  # Primary feed height
            "suggested_retract_height": positioning_analysis.get("feed_height"),  # Primary feed height
            "retract_candidates": positioning_analysis["positioning_heights"],
            "detected_move_speed": detected_move_speed,
            "detected_jog_speed": detected_jog_speed,
            "actual_cutting_speed": actual_cutting_speed,
            "actual_jog_speed": actual_jog_speed,
            "conversion_stats": self._calculate_conversion_stats(z_values, positioning_analysis["positioning_heights"]),
            "time_savings": self._calculate_time_savings(
                m3_coordinates, positioning_analysis["positioning_heights"], actual_cutting_speed, actual_jog_speed
            ),
        }

    def _analyze_positioning_heights(self, z_values: list[float]) -> dict[str, Any]:
        """Analyze Z values to find the feed height for optimization.

        Args:
            z_values: List of all Z values from M3 commands

        Returns:
            Dictionary with feed height analysis
        """
        z_counter = Counter(z_values)
        max_z = max(z_values)
        min_z = min(z_values)

        # Find heights that appear multiple times - keep all for analysis
        frequent_heights = [(z, count) for z, count in z_counter.items() if count >= 2]
        frequent_heights.sort(key=lambda x: x[0], reverse=True)

        # SAFETY RULE: Never jog on negative Z values (below material surface)
        positive_heights = [(z, count) for z, count in z_counter.items() if z >= 0 and count >= 2]
        avg_z = sum(z_values) / len(z_values)

        # Find the most frequent positive height - this is where we should jog
        # Simple and effective: highest frequency move above 0
        if positive_heights:
            # Sort by frequency (highest first), then by height (highest first) as tiebreaker
            positive_heights.sort(key=lambda x: (x[1], x[0]), reverse=True)
            feed_height = positive_heights[0][0]
            positioning_heights = [(feed_height, positive_heights[0][1])]
        else:
            feed_height = None
            positioning_heights = []

        return {
            "z_counter": z_counter,
            "max_z": max_z,
            "min_z": min_z,
            "avg_z": avg_z,
            "positioning_heights": positioning_heights,
            "feed_height": feed_height,
            "retract_height": feed_height,  # Keep for backward compatibility
            "frequent_heights": frequent_heights,
        }

    def _calculate_conversion_stats(
        self, z_values: list[float], positioning_heights: list[tuple[float, int]]
    ) -> dict[str, Any]:
        """Calculate statistics about what will be converted.

        Args:
            z_values: All Z values from M3 commands
            positioning_heights: List of (height, count) tuples for positioning

        Returns:
            Dictionary with conversion statistics
        """
        if not positioning_heights:
            return {
                "total_m3_commands": len(z_values),
                "positioning_commands": 0,
                "cutting_commands": len(z_values),
                "conversion_percentage": 0.0,
                "heights_to_convert": [],
            }

        heights_set = {h for h, _ in positioning_heights}
        positioning_commands = sum(1 for z in z_values if z in heights_set)
        cutting_commands = len(z_values) - positioning_commands
        conversion_percentage = (positioning_commands / len(z_values)) * 100 if z_values else 0

        return {
            "total_m3_commands": len(z_values),
            "positioning_commands": positioning_commands,
            "cutting_commands": cutting_commands,
            "conversion_percentage": conversion_percentage,
            "heights_to_convert": [h for h, _ in positioning_heights],
        }

    def _calculate_time_savings(
        self,
        m3_coordinates: list[tuple[float, float, float]],
        positioning_heights: list[tuple[float, int]],
        cutting_speed: float,
        jog_speed: float,
    ) -> dict[str, Any]:
        """Calculate estimated time savings from M3 to J3 conversion using actual distances.

        Args:
            m3_coordinates: List of (x, y, z) coordinates from M3 commands
            positioning_heights: List of (height, count) tuples for positioning
            cutting_speed: Actual cutting speed from file or configured
            jog_speed: Actual jog speed from file or configured

        Returns:
            Dictionary with time savings calculations
        """
        if not positioning_heights or not m3_coordinates:
            return {
                "positioning_commands": 0,
                "avg_move_distance": 0.0,
                "total_move_distance": 0.0,
                "time_at_cutting_speed": 0.0,
                "time_at_jog_speed": 0.0,
                "time_saved_minutes": 0.0,
                "time_saved_percentage": 0.0,
                "speed_improvement_factor": jog_speed / cutting_speed,
            }

        heights_set = {h for h, _ in positioning_heights}

        # Calculate actual distances between consecutive positioning moves
        positioning_coordinates = [(x, y, z) for x, y, z in m3_coordinates if z in heights_set]
        positioning_commands = len(positioning_coordinates)

        if positioning_commands <= 1:
            # Need at least 2 points to calculate distances
            return {
                "positioning_commands": positioning_commands,
                "avg_move_distance": 0.0,
                "total_move_distance": 0.0,
                "time_at_cutting_speed": 0.0,
                "time_at_jog_speed": 0.0,
                "time_saved_minutes": 0.0,
                "time_saved_percentage": 0.0,
                "speed_improvement_factor": jog_speed / cutting_speed,
            }

        # Calculate actual distances between consecutive positioning moves
        total_distance = 0.0
        for i in range(1, len(positioning_coordinates)):
            x1, y1, _z1 = positioning_coordinates[i - 1]
            x2, y2, _z2 = positioning_coordinates[i]

            # Calculate 2D distance (X,Y plane) since Z is the positioning height
            distance = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            total_distance += distance

        # Calculate average distance per move
        num_moves = len(positioning_coordinates) - 1
        avg_move_distance = total_distance / num_moves if num_moves > 0 else 0.0

        time_at_cutting_speed = total_distance / cutting_speed
        time_at_jog_speed = total_distance / jog_speed
        time_saved = time_at_cutting_speed - time_at_jog_speed

        # Calculate speed improvement factor
        speed_factor = jog_speed / cutting_speed

        return {
            "positioning_commands": positioning_commands,
            "avg_move_distance": avg_move_distance,
            "total_move_distance": total_distance,
            "time_at_cutting_speed": time_at_cutting_speed,
            "time_at_jog_speed": time_at_jog_speed,
            "time_saved_minutes": time_saved,
            "speed_improvement_factor": speed_factor,
            "cutting_speed_ipm": cutting_speed,
            "jog_speed_ipm": jog_speed,
        }

    def process_file(
        self,
        input_path: Path,
        output_path: Path | None = None,
        positioning_heights: list[float] | None = None,
        retract_height: float | None = None,  # Legacy support
        confirm_retract: bool = True,
    ) -> dict[str, Any]:
        """Process a .sbp file to convert M3 commands at positioning heights to J3.

        Args:
            input_path: Path to input .sbp file
            output_path: Path for output file (defaults to input_path with _shopbotjog suffix)
            positioning_heights: List of Z heights to convert (clearance, retract, etc.)
            retract_height: Single Z height (legacy, use positioning_heights instead)
            confirm_retract: Whether heights need confirmation

        Returns:
            Dictionary with processing results
        """
        # First analyze the file
        analysis = self.analyze_file(input_path)

        if "error" in analysis:
            return analysis

        # Determine positioning heights
        if positioning_heights is None:
            if retract_height is not None:
                # Legacy single height support
                positioning_heights = [retract_height]
            else:
                # Use detected positioning heights
                heights_data = analysis.get("positioning_heights", [])
                positioning_heights = [h for h, _ in heights_data]

        if not positioning_heights:
            return {"error": "Could not determine positioning heights"}

        self.positioning_heights = positioning_heights

        # Determine output behavior and backup strategy
        in_place_modification = output_path is None
        backup_path = None

        if in_place_modification:
            # In-place modification: modify original file and create backup
            output_path = input_path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = input_path.parent / f"{input_path.name}.{timestamp}.backup"

            try:
                shutil.copy2(input_path, backup_path)
            except OSError as e:
                return {"error": f"Failed to create backup: {e}"}
        else:
            # Custom output path: no backup needed
            pass

        # Process the file
        modifications = 0

        if in_place_modification:
            # For in-place modification, read everything first, then write back
            with open(input_path, encoding="utf-8") as infile:
                lines = infile.readlines()

            # Process lines in memory
            output_lines = []

            # Write header comment
            output_lines.append(f"' File modified by ShopBotJog v{self._get_version()}\n")
            if len(positioning_heights) == 1:
                output_lines.append(f"' Feed height detected as: {positioning_heights[0]}\n")
            else:
                heights_str = ", ".join(f"{h:.4f}" for h in sorted(positioning_heights, reverse=True))
                output_lines.append(f"' Feed heights detected as: {heights_str}\n")
            output_lines.append("' M3 commands at feed height converted to J3 for rapid jogging\n")
            output_lines.append(f"' Original file: {input_path.name}\n")
            output_lines.append("\n")

            for line in lines:
                original_line = line
                line_stripped = line.strip()

                # Check if this is an M3 command at positioning height
                match = self.m3_pattern.match(line_stripped)
                if match:
                    _, _, z = match.groups()
                    if float(z) in positioning_heights:
                        # Convert M3 to J3
                        new_line = line_stripped.replace("M3,", "J3,", 1)
                        output_lines.append(new_line + "\n")
                        modifications += 1
                        continue

                # Write original line if no modification needed
                output_lines.append(original_line)

            # Write back to the same file
            # output_path is guaranteed to be Path at this point (not None)
            assert output_path is not None
            with open(output_path, "w", encoding="utf-8") as outfile:
                outfile.writelines(output_lines)

        else:
            # For custom output path, use the original streaming approach
            # output_path is guaranteed to be Path at this point (not None)
            assert output_path is not None
            with open(input_path, encoding="utf-8") as infile, open(output_path, "w", encoding="utf-8") as outfile:
                # Write header comment
                outfile.write(f"' File modified by ShopBotJog v{self._get_version()}\n")
                if len(positioning_heights) == 1:
                    outfile.write(f"' Feed height detected as: {positioning_heights[0]}\n")
                else:
                    heights_str = ", ".join(f"{h:.4f}" for h in sorted(positioning_heights, reverse=True))
                    outfile.write(f"' Feed heights detected as: {heights_str}\n")
                outfile.write("' M3 commands at feed height converted to J3 for rapid jogging\n")
                outfile.write(f"' Original file: {input_path.name}\n")
                outfile.write("\n")

                for line in infile:
                    original_line = line
                    line_stripped = line.strip()

                    # Check if this is an M3 command at positioning height
                    match = self.m3_pattern.match(line_stripped)
                    if match:
                        _, _, z = match.groups()
                        if float(z) in positioning_heights:
                            # Convert M3 to J3
                            new_line = line_stripped.replace("M3,", "J3,", 1)
                            outfile.write(new_line + "\n")
                            modifications += 1
                            continue

                    # Write original line if no modification needed
                    outfile.write(original_line)

        self.modifications_made = modifications

        # Return detailed results including time savings
        conversion_stats = analysis.get("conversion_stats", {})
        time_savings = analysis.get("time_savings", {})

        result = {
            "input_file": str(input_path),
            "output_file": str(output_path),
            "positioning_heights": positioning_heights,
            "retract_height": positioning_heights[0] if positioning_heights else None,  # Legacy
            "modifications_made": modifications,
            "total_m3_commands": analysis["m3_commands"],
            "conversion_stats": conversion_stats,
            "time_savings": time_savings,
            "in_place_modification": in_place_modification,
            "success": True,
        }

        # Only include backup_file if a backup was created
        if backup_path is not None:
            result["backup_file"] = str(backup_path)

        return result

    def _get_version(self) -> str:
        """Get the current version."""
        try:
            from . import __version__

            return __version__
        except ImportError:
            return "0.1.0"

    def validate_sbp_file(self, file_path: Path) -> bool:
        """Validate that the file is a proper .sbp file.

        Args:
            file_path: Path to validate

        Returns:
            True if valid .sbp file
        """
        if not file_path.exists():
            return False

        if file_path.suffix.lower() != ".sbp":
            return False

        try:
            # Check if file contains ShopBot commands
            with open(file_path, encoding="utf-8") as f:
                content = f.read(1000)  # Read first 1KB
                # Look for common ShopBot commands
                shopbot_indicators = ["SA", "M3,", "J2,", "J3,", "TR,", "CN,"]
                return any(indicator in content for indicator in shopbot_indicators)
        except (OSError, UnicodeDecodeError):
            return False
