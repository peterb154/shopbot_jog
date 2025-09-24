"""Command-line interface for ShopBotJog."""

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, FloatPrompt
from rich.table import Table
from rich.text import Text

from .core import ShopBotJogProcessor

console = Console()


def print_banner() -> None:
    """Print the ShopBotJog banner."""
    banner = Text("🤖 ShopBotJog", style="bold blue")
    subtitle = Text("Optimizing rapid jog movements in Fusion 360 ShopBot files", style="dim")
    console.print(Panel.fit(f"{banner}\n{subtitle}", border_style="blue"))


def print_analysis_results(analysis: dict) -> None:
    """Print enhanced file analysis results."""
    # Basic file info table
    basic_table = Table(title="📊 File Analysis", border_style="blue")
    basic_table.add_column("Metric", style="cyan", no_wrap=True)
    basic_table.add_column("Value", style="white")

    basic_table.add_row("Total Lines", str(analysis["total_lines"]))
    basic_table.add_row("M3 Commands Found", str(analysis["m3_commands"]))
    basic_table.add_row("Z Height Range", f"{analysis.get('min_z', 0):.4f} to {analysis.get('max_z', 0):.4f}")

    console.print(basic_table)
    console.print()

    # Feed height detection - show all positive heights
    all_heights = analysis.get("frequent_heights", [])
    # Only show heights that appear at least twice
    positive_heights = [(h, c) for h, c in all_heights if h >= 0 and c >= 2]

    # Debug: also check z_counter for all positive heights
    z_counter = analysis.get("z_counter", {})
    if not positive_heights and z_counter:
        positive_heights = [(h, c) for h, c in z_counter.items() if h >= 0 and c >= 2]

    if positive_heights:
        heights_table = Table(title="🎯 Positioning Heights Analysis", border_style="green")
        heights_table.add_column("Height (inches)", style="yellow", justify="right")
        heights_table.add_column("Occurrences", style="white", justify="right")
        heights_table.add_column("Selection", style="cyan", no_wrap=True)

        feed = analysis.get("feed_height")

        # Sort by frequency (highest first) for display
        positive_heights.sort(key=lambda x: x[1], reverse=True)

        for height, count in positive_heights:
            if feed is not None and abs(height - feed) < 0.0001:  # Use tolerance for float comparison
                selection = "Feed Height (Target)"
            else:
                selection = "Positioning Move"

            heights_table.add_row(f"{height:.4f}", str(count), selection)

        console.print(heights_table)
        console.print()

        # Add explanation
        if feed is not None:
            occurrences = analysis["z_counter"][feed]
            console.print(
                f"[dim]💡 Feed height selected as most frequent positioning move: "
                f"{feed:.4f} ({occurrences} occurrences)[/dim]"
            )
        else:
            console.print(f"[dim]⚠️  No clear feed height detected (feed={feed})[/dim]")
        console.print()

    # Conversion statistics
    conv_stats = analysis.get("conversion_stats", {})
    if conv_stats:
        stats_table = Table(title="🔄 Feed Height Optimization", border_style="yellow")
        stats_table.add_column("Metric", style="cyan", no_wrap=True)
        stats_table.add_column("Value", style="white")

        stats_table.add_row("Total M3 Commands", str(conv_stats.get("total_m3_commands", 0)))
        stats_table.add_row("Feed Commands", f"[green]{conv_stats.get('positioning_commands', 0)}[/green]")
        stats_table.add_row("Cutting Commands", f"[dim]{conv_stats.get('cutting_commands', 0)}[/dim]")
        percentage = conv_stats.get("conversion_percentage", 0)
        stats_table.add_row("Commands to Optimize", f"[bold green]{percentage:.1f}%[/bold green]")

        console.print(stats_table)
        console.print()

    # Time savings estimates
    time_savings = analysis.get("time_savings", {})
    if time_savings and time_savings.get("positioning_commands", 0) > 0:
        savings_table = Table(title="⚡ Feed Movement Time Savings", border_style="red")
        savings_table.add_column("Metric", style="cyan", no_wrap=True)
        savings_table.add_column("Value", style="white")

        cutting_speed = time_savings.get("cutting_speed_ipm", 60)
        jog_speed = time_savings.get("jog_speed_ipm", 300)
        time_saved = time_savings.get("time_saved_minutes", 0)
        speed_factor = time_savings.get("speed_improvement_factor", 1)

        # Show if speeds were detected from file
        detected_move = analysis.get("detected_move_speed")
        detected_jog = analysis.get("detected_jog_speed")

        move_display = f"{cutting_speed} IPM"
        if detected_move is not None:
            move_display += " [dim](from MS command)[/dim]"
        else:
            move_display += " [dim](fallback default)[/dim]"

        jog_display = f"[green]{jog_speed} IPM[/green]"
        if detected_jog is not None:
            jog_display += " [dim](from JS command)[/dim]"
        else:
            jog_display += " [dim](fallback default)[/dim]"

        savings_table.add_row("Current Speed (M3)", move_display)
        savings_table.add_row("Jog Speed (J3)", jog_display)
        savings_table.add_row("Speed Improvement", f"[bold green]{speed_factor:.1f}x faster[/bold green]")

        if time_saved >= 1:
            time_display = f"[bold red]{time_saved:.1f} minutes[/bold red]"
        else:
            time_display = f"[bold red]{time_saved * 60:.0f} seconds[/bold red]"

        savings_table.add_row("Estimated Time Saved", time_display)

        console.print(savings_table)
        console.print()

        # Distance calculation note
        total_distance = time_savings.get("total_move_distance", 0)
        avg_distance = time_savings.get("avg_move_distance", 0)
        if total_distance > 0:
            console.print(
                f"[dim]📏 Calculated from {total_distance:.1f} inches total distance, "
                f"{avg_distance:.1f} inch average per move[/dim]"
            )
        else:
            console.print("[dim]💡 Estimates based on 2-inch average move distance[/dim]")


def print_results(results: dict) -> None:
    """Print processing results."""
    if results.get("success", False):
        console.print("✅ [green]Successfully processed file![/green]")

        # Show backup info only if backup was created (in-place modification)
        if "backup_file" in results:
            console.print(f"💾 Backup created: {results['backup_file']}")

        # Show appropriate output message based on modification type
        if results.get("in_place_modification", False):
            console.print(f"📝 Modified file in-place: {results['output_file']}")
        else:
            console.print(f"📁 Output file created: {results['output_file']}")

        console.print(f"📏 Feed height: {results['retract_height']:.4f}")
        console.print(f"🔄 Modified {results['modifications_made']} out of {results['total_m3_commands']} M3 commands")

        if results["modifications_made"] > 0:
            modifications = results["modifications_made"]
            console.print(
                f"🚀 [bold green]Your ShopBot will now jog {modifications} movements at rapid speed![/bold green]"
            )
        else:
            console.print(
                "i  [yellow]No modifications were made - no M3 commands found at specified feed height.[/yellow]"
            )
    else:
        error_msg = results.get("error", "Unknown error occurred")
        console.print(f"❌ [red]Error: {error_msg}[/red]")


@click.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Custom output file path (default: modifies input file in-place with backup)",
)
@click.option("--yes", "-y", is_flag=True, help="Automatically confirm detected feed height")
@click.option("--analyze-only", "-a", is_flag=True, help="Only analyze the file, don't modify it")
@click.option("--quiet", "-q", is_flag=True, help="Suppress banner and verbose output")
@click.option(
    "--cutting-speed",
    type=float,
    default=60.0,
    help="Fallback cutting speed in IPM for time calculations if MS command not found (default: 60)",
)
@click.option(
    "--jog-speed",
    type=float,
    default=300.0,
    help="Fallback jog speed in IPM for time calculations if JS command not found (default: 300)",
)
@click.option("--feed-height", type=float, help="Manually specify feed height (primary optimization target)")
def main(
    input_file: Path,
    output: Path | None,
    yes: bool,
    analyze_only: bool,
    quiet: bool,
    cutting_speed: float,
    jog_speed: float,
    feed_height: float | None,
) -> None:
    """ShopBotJog: Convert M3 commands to J3 at feed height for rapid ShopBot operation.

    Focuses on optimizing feed height movements for maximum speed improvement during
    positioning moves between cutting operations.

    INPUT_FILE: Path to the .sbp file to process
    """
    if not quiet:
        print_banner()

    processor = ShopBotJogProcessor()
    # Configure speeds for time calculations
    processor.cutting_speed_ipm = cutting_speed
    processor.jog_speed_ipm = jog_speed

    # Validate input file
    if not processor.validate_sbp_file(input_file):
        console.print("❌ [red]Error: Invalid .sbp file or file doesn't contain ShopBot commands[/red]")
        raise click.Abort()

    try:
        # Analyze the file
        if not quiet:
            console.print(f"🔍 Analyzing file: {input_file}")

        analysis = processor.analyze_file(input_file)

        if "error" in analysis:
            console.print(f"❌ [red]Error: {analysis['error']}[/red]")
            raise click.Abort()

        if not quiet:
            print_analysis_results(analysis)

        # If analyze-only mode, stop here
        if analyze_only:
            console.print("📊 [blue]Analysis complete. Use without --analyze-only to process the file.[/blue]")
            return

        # Determine feed height
        positioning_heights: list[float] = []
        manual_height_specified = feed_height is not None and feed_height >= 0

        # Check for manually specified feed height
        if manual_height_specified:
            # Validate that the specified height exists in the file
            z_counter = analysis.get("z_counter", {})
            available_heights = [h for h in z_counter.keys() if h >= 0]

            if feed_height not in z_counter:
                console.print(
                    f"❌ [red]Error: Manually specified feed height {feed_height:.4f} not found in file[/red]"
                )
                if available_heights:
                    console.print("Available positive heights in file:")
                    for height in sorted(available_heights, reverse=True):
                        occurrences = z_counter[height]
                        console.print(f"  • {height:.4f} ({occurrences} occurrences)")
                else:
                    console.print("No positive Z heights found in file.")
                raise click.Abort()

            # feed_height is guaranteed to be float here due to validation above
            assert feed_height is not None
            positioning_heights = [feed_height]
            if not quiet:
                console.print(f"📐 Using manually specified feed height: {feed_height:.4f}")
        else:
            # Use auto-detected feed height
            positioning_heights = [h for h, _ in analysis.get("positioning_heights", [])]

            if not positioning_heights:
                console.print(
                    "❌ [red]Could not auto-detect feed height. Please specify manually with --feed-height[/red]"
                )
                raise click.Abort()

        # Ask for confirmation unless --yes flag is used OR manual height is specified
        if not yes and not manual_height_specified:
            if len(positioning_heights) == 1:
                console.print(f"\n🎯 Detected feed height: [bold]{positioning_heights[0]:.4f}[/bold]")
            else:
                heights_str = ", ".join(f"{h:.4f}" for h in sorted(positioning_heights, reverse=True))
                console.print(f"\n🎯 Will convert at heights: [bold]{heights_str}[/bold]")

            console.print(
                "These heights will be converted from M3 (cutting speed) "
                "to J3 (rapid jog speed) for faster positioning between cuts."
            )

            if not Confirm.ask("Proceed with these height conversions?"):
                feed_height_input = FloatPrompt.ask("Please enter the feed height to convert")
                positioning_heights = [feed_height_input]

        # Process the file
        if not quiet:
            if len(positioning_heights) == 1:
                console.print(f"⚙️  Processing file with feed height: {positioning_heights[0]:.4f}")
            else:
                heights_str = ", ".join(f"{h:.4f}" for h in sorted(positioning_heights, reverse=True))
                console.print(f"⚙️  Processing file with heights: {heights_str}")

        # Process using positioning heights
        results = processor.process_file(
            input_path=input_file, output_path=output, positioning_heights=positioning_heights, confirm_retract=False
        )

        print_results(results)

    except KeyboardInterrupt:
        console.print("\n❌ [red]Operation cancelled by user[/red]")
        raise click.Abort()
    except click.Abort:
        # Re-raise click.Abort to let Click handle it properly
        raise
    except Exception as e:
        console.print(f"❌ [red]Unexpected error: {e!s}[/red]")
        if not quiet:
            console.print("Please report this issue at: https://github.com/peterb154/shopbot_jog/issues")
        raise click.Abort()


if __name__ == "__main__":
    main()
