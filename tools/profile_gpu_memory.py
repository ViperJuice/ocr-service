#!/usr/bin/env python3
"""
GPU Memory Profiling Script for OCR Service

Measures actual GPU memory consumption across different configurations and compares
against calculated forecasts to identify memory estimation errors.

Usage:
    python tools/profile_gpu_memory.py --output profiling_results/
    python tools/profile_gpu_memory.py --models deepseek-ocr qwen2-vl-2b --dpi 300 600
    python tools/profile_gpu_memory.py --quick  # Test only essential configs
"""

import sys
import os
from pathlib import Path
import json
import click
from datetime import datetime
from PIL import Image

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.memory_profiler import MemoryProfiler
from src.models.model_manager import ModelManager
from config.settings import get_settings


def create_sample_image(dpi: int) -> Image.Image:
    """
    Create sample image for testing at specified DPI.

    Args:
        dpi: Target DPI (affects image dimensions)

    Returns:
        PIL Image suitable for model inference testing
    """
    # Calculate dimensions: 8.5x11 inch page at specified DPI
    width = int(8.5 * dpi)
    height = int(11 * dpi)

    # Create white background with some text-like patterns
    img = Image.new('RGB', (width, height), color='white')

    # Note: For real profiling, you could load an actual sample PDF page
    # For now, a blank image is sufficient to trigger memory allocation

    return img


def generate_markdown_report(report_data: dict, output_path: Path):
    """
    Generate human-readable Markdown report.

    Args:
        report_data: Report dictionary from ProfileReport.to_dict()
        output_path: Path to write markdown file
    """
    md_lines = []

    # Header
    md_lines.append("# GPU Memory Profiling Report")
    md_lines.append(f"\n**Generated:** {report_data['metadata']['timestamp']}")
    md_lines.append(f"**Total Tests:** {report_data['metadata']['total_tests']}")
    md_lines.append(f"**Successful:** {report_data['metadata']['successful_tests']}")
    md_lines.append(f"**Failed:** {report_data['metadata']['failed_tests']}")

    # System Info
    md_lines.append("\n## System Configuration\n")
    sys_info = report_data['system_info']
    md_lines.append(f"- **CUDA Version:** {sys_info['cuda_version']}")
    md_lines.append(f"- **GPU Count:** {sys_info['gpu_count']}")

    for gpu in sys_info['gpus']:
        md_lines.append(f"- **GPU {gpu['id']}:** {gpu['name']} ({gpu['total_memory_gb']}GB)")

    # Summary Statistics
    md_lines.append("\n## Summary Statistics\n")
    summary = report_data['summary']
    md_lines.append(f"- **Average Forecast Error:** {summary['avg_error_pct']:.1f}%")
    md_lines.append(f"- **Max Error:** {summary['max_error_pct']:.1f}%")
    md_lines.append(f"- **Min Error:** {summary['min_error_pct']:.1f}%")
    md_lines.append(f"- **Underestimated (>5%):** {summary['underestimated_count']} tests")
    md_lines.append(f"- **Overestimated (>5%):** {summary['overestimated_count']} tests")

    # Detailed Results Table
    md_lines.append("\n## Detailed Measurements\n")
    md_lines.append("| Model | DPI | Crop | Calc Peak | Actual Peak | Error % | Status |")
    md_lines.append("|-------|-----|------|-----------|-------------|---------|--------|")

    for m in report_data['measurements']:
        status = "✓" if m['success'] else "✗"
        error_pct = m['analysis']['forecast_error_pct']
        error_str = f"{error_pct:+.1f}%" if m['success'] else "N/A"

        md_lines.append(
            f"| {m['model_name']} | {m['dpi']} | "
            f"{'Yes' if m['crop_mode_enabled'] else 'No'} | "
            f"{m['calculated']['peak_gb']:.1f}GB | "
            f"{m['actual']['inference_peak_gb']:.1f}GB | "
            f"{error_str} | {status} |"
        )

    # Recommendations
    md_lines.append("\n## Recommendations\n")

    if summary['underestimated_count'] > 0:
        md_lines.append("### ⚠️ Memory Underestimation Detected\n")
        md_lines.append(f"Found {summary['underestimated_count']} configurations where calculated memory is **more than 5% below** actual usage.\n")
        md_lines.append("**Action Required:** Increase memory overhead multipliers in `src/models/gpu_memory_analyzer.py`\n")

        # Find worst offenders
        underestimated = [
            m for m in report_data['measurements']
            if m['success'] and m['analysis']['underestimated']
        ]
        underestimated.sort(key=lambda x: x['analysis']['forecast_error_pct'])

        md_lines.append("**Worst Cases:**\n")
        for m in underestimated[:3]:
            md_lines.append(
                f"- {m['model_name']} @ {m['dpi']}DPI: "
                f"{m['analysis']['forecast_error_pct']:.1f}% error "
                f"({m['calculated']['peak_gb']:.1f}GB calc vs "
                f"{m['actual']['inference_peak_gb']:.1f}GB actual)"
            )

    if summary['overestimated_count'] > 0:
        md_lines.append("\n### ℹ️ Memory Overestimation Detected\n")
        md_lines.append(f"Found {summary['overestimated_count']} configurations where calculated memory is **more than 5% above** actual usage.\n")
        md_lines.append("**Optional:** Consider reducing memory overhead multipliers for better GPU utilization.\n")

    if summary['underestimated_count'] == 0 and summary['overestimated_count'] == 0:
        md_lines.append("### ✅ Memory Calculations Accurate\n")
        md_lines.append("All measurements within ±5% of forecasts. No tuning needed.\n")

    # Write file
    output_path.write_text("\n".join(md_lines))


def generate_csv_report(report_data: dict, output_path: Path):
    """
    Generate CSV report for spreadsheet analysis.

    Args:
        report_data: Report dictionary from ProfileReport.to_dict()
        output_path: Path to write CSV file
    """
    import csv

    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            "Model", "DPI", "Crop Mode", "Strategy",
            "Calc Base (GB)", "Calc Overhead (GB)", "Calc Peak (GB)",
            "Actual Load (GB)", "Actual Peak (GB)",
            "Forecast Error (%)", "Underestimated", "Success", "Error Message"
        ])

        # Data rows
        for m in report_data['measurements']:
            writer.writerow([
                m['model_name'],
                m['dpi'],
                "Yes" if m['crop_mode_enabled'] else "No",
                m['strategy_name'],
                m['calculated']['base_gb'],
                m['calculated']['overhead_gb'],
                m['calculated']['peak_gb'],
                m['actual']['load_gb'],
                m['actual']['inference_peak_gb'],
                m['analysis']['forecast_error_pct'] if m['success'] else "N/A",
                "Yes" if m.get('analysis', {}).get('underestimated', False) else "No",
                "Yes" if m['success'] else "No",
                m.get('error_message', '')
            ])


@click.command()
@click.option(
    '--models',
    multiple=True,
    default=['deepseek-ocr', 'qwen2-vl-2b', 'qwen2-vl-7b'],
    help='Models to profile (can specify multiple times)'
)
@click.option(
    '--dpi',
    multiple=True,
    type=int,
    default=[150, 300, 600],
    help='DPI settings to test (can specify multiple times)'
)
@click.option(
    '--output',
    type=click.Path(path_type=Path),
    default=Path('profiling_results'),
    help='Output directory for reports'
)
@click.option(
    '--quick',
    is_flag=True,
    help='Quick mode: test only essential configs (300 DPI, no crop)'
)
@click.option(
    '--verbose/--quiet',
    default=True,
    help='Print detailed progress messages'
)
def main(models, dpi, output, quick, verbose):
    """
    Profile GPU memory usage across different model configurations.

    Measures actual VRAM consumption and compares against calculated forecasts
    to identify memory estimation errors.
    """
    # Ensure output directory exists
    output.mkdir(parents=True, exist_ok=True)

    # Initialize
    profiler = MemoryProfiler(verbose=verbose)

    # Load model configurations
    settings = get_settings()
    model_configs = settings.load_model_configs()
    model_manager = ModelManager(model_configs["models"])

    timestamp = datetime.now().isoformat()

    if verbose:
        print("=" * 80)
        print("GPU Memory Profiling")
        print("=" * 80)
        print(f"Models: {', '.join(models)}")
        print(f"DPI settings: {', '.join(map(str, dpi))}")
        print(f"Quick mode: {quick}")
        print()

    # Build test matrix
    test_configs = []

    for model_name in models:
        for dpi_val in dpi:
            # Test with crop mode enabled (if applicable)
            if model_name == "deepseek-ocr" and not quick:
                test_configs.append({
                    'model_name': model_name,
                    'dpi': dpi_val,
                    'disable_crop_mode': False
                })

            # Test with crop mode disabled (or N/A for non-DeepSeek)
            test_configs.append({
                'model_name': model_name,
                'dpi': dpi_val,
                'disable_crop_mode': True
            })

    # Quick mode: reduce to essential tests
    if quick:
        test_configs = [
            c for c in test_configs
            if c['dpi'] == 300 and c['disable_crop_mode']
        ]

    if verbose:
        print(f"Total tests to run: {len(test_configs)}\n")

    # Run tests
    for i, config in enumerate(test_configs, 1):
        if verbose:
            print(f"\n{'='*80}")
            print(f"Test {i}/{len(test_configs)}")
            print('='*80)

        # Create sample image for this DPI
        sample_image = create_sample_image(config['dpi'])

        # Run measurement
        profiler.measure_model_loading(
            model_manager=model_manager,
            model_name=config['model_name'],
            dpi=config['dpi'],
            disable_crop_mode=config['disable_crop_mode'],
            strategy_name="single_gpu_sequential",  # Use sequential for profiling
            device_ids=[0],
            sample_image=sample_image
        )

    # Generate reports
    if verbose:
        print("\n" + "="*80)
        print("Generating Reports")
        print("="*80)

    report = profiler.generate_report(timestamp)
    report_dict = report.to_dict()

    # JSON report
    json_path = output / f"memory_profile_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(json_path, 'w') as f:
        json.dump(report_dict, f, indent=2)

    if verbose:
        print(f"✓ JSON report: {json_path}")

    # Markdown report
    md_path = json_path.with_suffix('.md')
    generate_markdown_report(report_dict, md_path)

    if verbose:
        print(f"✓ Markdown report: {md_path}")

    # CSV report
    csv_path = json_path.with_suffix('.csv')
    generate_csv_report(report_dict, csv_path)

    if verbose:
        print(f"✓ CSV report: {csv_path}")

    # Print summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total tests: {report_dict['metadata']['total_tests']}")
    print(f"Successful: {report_dict['metadata']['successful_tests']}")
    print(f"Failed: {report_dict['metadata']['failed_tests']}")
    print(f"\nAverage forecast error: {report_dict['summary']['avg_error_pct']:.1f}%")
    print(f"Underestimated (>5%): {report_dict['summary']['underestimated_count']} tests")
    print(f"Overestimated (>5%): {report_dict['summary']['overestimated_count']} tests")

    if report_dict['summary']['underestimated_count'] > 0:
        print("\n⚠️  WARNING: Memory underestimation detected!")
        print("    Review markdown report for tuning recommendations.")
    else:
        print("\n✅ Memory calculations accurate within tolerance.")

    print(f"\nFull report: {md_path}")


if __name__ == '__main__':
    main()
