"""Speed analysis and time savings calculations for LibertyJog."""

from typing import Any


class SpeedAnalyzer:
    """Handles speed detection and time savings calculations."""

    def __init__(self, default_cutting_speed: float = 60.0, default_jog_speed: float = 300.0) -> None:
        """Initialize the speed analyzer.

        Args:
            default_cutting_speed: Default cutting speed in IPM
            default_jog_speed: Default jog speed in IPM
        """
        self.default_cutting_speed = default_cutting_speed
        self.default_jog_speed = default_jog_speed

    def calculate_conversion_stats(
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

    def calculate_time_savings(
        self,
        z_values: list[float],
        positioning_heights: list[tuple[float, int]],
        cutting_speed: float,
        jog_speed: float,
    ) -> dict[str, Any]:
        """Calculate estimated time savings from M3 to J3 conversion.

        Args:
            z_values: All Z values from M3 commands
            positioning_heights: List of (height, count) tuples for positioning
            cutting_speed: Actual cutting speed from file or configured
            jog_speed: Actual jog speed from file or configured

        Returns:
            Dictionary with time savings calculations
        """
        if not positioning_heights or not z_values:
            return {
                "positioning_commands": 0,
                "avg_move_distance": 0.0,
                "time_at_cutting_speed": 0.0,
                "time_at_jog_speed": 0.0,
                "time_saved_minutes": 0.0,
                "time_saved_percentage": 0.0,
                "speed_improvement_factor": jog_speed / cutting_speed,
            }

        heights_set = {h for h, _ in positioning_heights}
        positioning_commands = sum(1 for z in z_values if z in heights_set)

        # Estimate average move distance (conservative approximation)
        # In reality, we'd need X,Y coordinates to calculate actual distances
        avg_move_distance = 2.0  # inches (conservative estimate)

        time_at_cutting_speed = (positioning_commands * avg_move_distance) / cutting_speed
        time_at_jog_speed = (positioning_commands * avg_move_distance) / jog_speed
        time_saved = time_at_cutting_speed - time_at_jog_speed

        # Calculate percentage improvement
        speed_factor = jog_speed / cutting_speed
        time_saved_percentage = ((speed_factor - 1) / speed_factor) * 100

        return {
            "positioning_commands": positioning_commands,
            "avg_move_distance": avg_move_distance,
            "time_at_cutting_speed": time_at_cutting_speed,
            "time_at_jog_speed": time_at_jog_speed,
            "time_saved_minutes": time_saved,
            "time_saved_percentage": time_saved_percentage,
            "speed_improvement_factor": speed_factor,
            "cutting_speed_ipm": cutting_speed,
            "jog_speed_ipm": jog_speed,
        }
