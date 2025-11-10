"""Click-based CLI commands for OCR service."""
import click
from pathlib import Path
from typing import Optional
from PIL import Image
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import get_settings
from src.models import ModelManager
from src.preprocessing import preprocess_image, extract_images_from_pdf, validate_file_extension, validate_file_size
from src.utils import get_gpu_info, get_memory_summary

console = Console()


def infer_format_from_extension(output_path: Path) -> str:
    """
    Infer output format from file extension.
    
    Args:
        output_path: Path to output file
        
    Returns:
        Format string: "text", "markdown", or "json"
    """
    extension = output_path.suffix.lower()
    if extension == ".md":
        return "markdown"
    elif extension == ".json":
        return "json"
    else:
        return "text"


def validate_format_extension_match(format: str, output_path: Path) -> None:
    """
    Validate that explicit format matches output file extension.
    
    Args:
        format: Explicitly specified format
        output_path: Path to output file
        
    Raises:
        click.BadParameter: If format and extension don't match
    """
    inferred_format = infer_format_from_extension(output_path)
    
    # Map formats to expected extensions for error messages
    format_to_ext = {
        "text": ".txt",
        "markdown": ".md",
        "json": ".json"
    }
    
    if format != inferred_format:
        raise click.BadParameter(
            f"Format '{format}' conflicts with output extension '{output_path.suffix}'. "
            f"Expected extension '{format_to_ext.get(format, '.txt')}' for format '{format}'."
        )


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """OCR Service - Production-ready OCR using vision-language models."""
    pass


@cli.command()
@click.argument("image_path", type=click.Path(exists=True))
@click.option(
    "--model",
    "-m",
    type=click.Choice(["qwen3-vl-8b", "qwen3-vl-4b", "qwen3-vl-2b", "deepseek-ocr"], case_sensitive=False),
    default=None,
    help="Model to use (default: from config)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output file path (default: print to console)",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["text", "markdown", "json"], case_sensitive=False),
    default="text",
    help="Output format",
)
@click.option(
    "--no-preprocess",
    is_flag=True,
    help="Skip image preprocessing",
)
def ocr(
    image_path: str,
    model: Optional[str],
    output: Optional[str],
    format: str,
    no_preprocess: bool,
):
    """
    Extract text from an image using OCR.
    
    Example:
        ocr image.jpg
        ocr document.png --model qwen3-vl-8b --output result.txt
        ocr scan.jpg --format markdown -o output.md
    """
    try:
        # Load settings
        settings = get_settings()
        model_configs = settings.load_model_configs()
        
        # Use default model if not specified
        if model is None:
            model = settings.default_model
        
        console.print(f"[bold blue]OCR Service[/bold blue]")
        console.print(f"Image: {image_path}")
        console.print(f"Model: {model}")
        console.print(f"Format: {format}\n")
        
        # Validate input file
        image_path = Path(image_path)
        validate_file_extension(image_path, allowed_extensions=(".jpg", ".jpeg", ".png", ".tiff", ".tif"))
        validate_file_size(image_path, max_size_mb=settings.max_upload_size_mb)
        
        # Load image
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Loading image...", total=None)
            image = Image.open(image_path)
            
            # Preprocess if enabled
            if not no_preprocess:
                progress.update(task, description="Preprocessing image...")
                image = preprocess_image(image, max_size=settings.max_image_size)
            
            progress.update(task, description=f"Loading model: {model}...")
            
            # Initialize model manager
            manager = ModelManager(model_configs["models"])
            manager.load_model(model)
            
            progress.update(task, description="Processing image...")
            
            # Process image
            prompt_type = "markdown" if format == "markdown" else "ocr"
            result = manager.get_current_model().process_image(image, prompt_type=prompt_type)
            
            progress.update(task, description="Done!", completed=True)
        
        # Display results
        console.print("\n[bold green]✓ OCR Complete[/bold green]")
        console.print(f"Processing time: {result.processing_time:.2f}s")
        console.print(f"Memory usage: {result.metadata.get('memory_usage', {})}\n")
        
        # Output text
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(result.text, encoding="utf-8")
            console.print(f"[green]Results saved to: {output}[/green]")
        else:
            console.print("[bold cyan]Extracted Text:[/bold cyan]")
            console.print("─" * 80)
            console.print(result.text)
            console.print("─" * 80)
        
        # Clean up
        manager.unload_all()
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}", style="red")
        raise click.Abort()


@cli.command()
@click.argument("pdf_path", type=click.Path(exists=True))
@click.option(
    "--model",
    "-m",
    type=click.Choice(["qwen3-vl-8b", "qwen3-vl-4b", "qwen3-vl-2b", "deepseek-ocr"], case_sensitive=False),
    default=None,
    help="Model to use",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    required=True,
    help="Output file path",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["text", "markdown", "json"], case_sensitive=False),
    default=None,
    help="Output format (inferred from file extension if not specified)",
)
@click.option(
    "--context",
    type=str,
    default=None,
    help="Document description to guide formatting (e.g., 'Legal deposition with line numbers')",
)
@click.option(
    "--max-pages",
    type=int,
    default=None,
    help="Maximum number of pages to process",
)
@click.option(
    "--dpi",
    type=int,
    default=300,
    help="DPI for PDF rendering",
)
@click.option(
    "--method",
    type=click.Choice(["auto", "extract", "ocr", "hybrid"], case_sensitive=False),
    default="auto",
    help="Processing method: auto (smart detect), extract (PDF text only), ocr (image OCR only), hybrid (both + AI merge)",
)
@click.option(
    "--force-ocr",
    is_flag=True,
    help="Force OCR even if embedded text exists",
)
@click.option(
    "--min-text-chars",
    type=int,
    default=10,
    help="Minimum characters to consider page as having text (default: 10)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed processing information",
)
@click.option(
    "--quantization",
    type=click.Choice(["int8", "int4"], case_sensitive=False),
    default=None,
    help="Model quantization (reduces memory, may reduce quality)",
)
@click.option(
    "--gpu-strategy",
    type=click.Choice(["auto", "dual", "sequential", "sharded"], case_sensitive=False),
    default="auto",
    help="GPU loading strategy: auto (detect), dual (separate GPUs), sequential (swap models), sharded (split large models)",
)
@click.option(
    "--incremental",
    is_flag=True,
    help="Incremental mode: unload model between steps (slower, less memory)",
)
@click.option(
    "--no-memory-opt",
    is_flag=True,
    help="Disable automatic memory optimizations",
)
@click.option(
    "--no-oom-recovery",
    is_flag=True,
    help="Disable automatic OOM recovery via image resizing",
)
@click.option(
    "--enable-spatial-hints",
    is_flag=True,
    default=True,
    help="Enable spatial hint extraction (Phase 1)",
)
@click.option(
    "--enable-bbox-annotations",
    is_flag=True,
    help="Draw bounding boxes on images for visual grounding (Phase 2)",
)
@click.option(
    "--enable-calibration",
    is_flag=True,
    help="Enable calibration mode: process first N pages for approval (Phase 3)",
)
@click.option(
    "--calibration-pages",
    type=int,
    default=3,
    help="Number of pages to use for calibration (default: 3)",
)
@click.option(
    "--skip-approval",
    is_flag=True,
    help="Skip interactive approval step (auto-approve calibration)",
)
@click.option(
    "--disable-crop-mode",
    is_flag=True,
    help="Disable DeepSeek crop mode to reduce memory usage (~50% savings, may reduce OCR quality)"
)
@click.option(
    "--profile-memory",
    is_flag=True,
    help="Enable dynamic memory profiling to improve future runs (learns actual memory usage)"
)
@click.option(
    "--merge-model",
    type=click.Choice(["auto", "qwen3-vl-8b", "qwen3-vl-4b", "qwen3-vl-2b"], case_sensitive=False),
    default="auto",
    help="Merge/format model: auto (smart selection based on VRAM), 7b (best quality), 2b (fastest)"
)
@click.option(
    "--prefer-speed",
    is_flag=True,
    help="Prioritize speed over quality when auto-selecting models (uses smaller models)"
)
@click.option(
    "--enable-validation",
    is_flag=True,
    help="Enable extraction validation with optional refinement (adds 1-20s per page, improves consistency)"
)
@click.option(
    "--no-resume",
    is_flag=True,
    help="Disable automatic resume from checkpoint (start from beginning)"
)
@click.option(
    "--no-checkpointing",
    is_flag=True,
    help="Disable checkpoint/resume functionality completely"
)
@click.option(
    "--no-monitoring",
    is_flag=True,
    help="Disable system resource monitoring"
)
@click.option(
    "--monitor-interval",
    type=int,
    default=30,
    help="System monitoring interval in seconds (default: 30)"
)
@click.option(
    "--staged-pipeline",
    is_flag=True,
    default=False,
    help="Use staged pipeline processing (recommended for stability)"
)
def pdf(
    pdf_path: str,
    model: Optional[str],
    output: str,
    format: Optional[str],
    context: Optional[str],
    max_pages: Optional[int],
    dpi: int,
    method: str,
    force_ocr: bool,
    min_text_chars: int,
    verbose: bool,
    quantization: Optional[str],
    gpu_strategy: str,
    incremental: bool,
    no_memory_opt: bool,
    no_oom_recovery: bool,
    enable_spatial_hints: bool,
    enable_bbox_annotations: bool,
    enable_calibration: bool,
    calibration_pages: int,
    skip_approval: bool,
    disable_crop_mode: bool,
    profile_memory: bool,
    merge_model: str,
    prefer_speed: bool,
    enable_validation: bool,
    no_resume: bool,
    no_checkpointing: bool,
    no_monitoring: bool,
    monitor_interval: int,
    staged_pipeline: bool,
):
    """
    Extract text from a PDF document with intelligent hybrid processing.

    The command automatically detects embedded text and chooses the best method:
    - Pages with embedded text: Extract + OCR + AI merge for accuracy
    - Pages without text (scanned): OCR only

    Processing Modes:
    - Default: Page-by-page hybrid processing with model switching
    - Staged Pipeline (--staged-pipeline): Process all pages through OCR, then merge
      (recommended for stability, eliminates memory fragmentation)

    Examples:
        ocr pdf document.pdf -o result.txt
        ocr pdf scan.pdf -o result.txt --method ocr --dpi 200
        ocr pdf mixed.pdf -o result.txt --verbose
        ocr pdf text.pdf -o result.txt --force-ocr
        ocr pdf large.pdf -o result.txt --staged-pipeline
    """
    try:
        # Load settings
        settings = get_settings()
        model_configs = settings.load_model_configs()
        
        if model is None:
            model = settings.default_model
        
        console.print(f"[bold blue]OCR Service - Hybrid PDF Processing[/bold blue]")
        console.print(f"PDF: {pdf_path}")
        console.print(f"Model: {model}")
        console.print(f"Method: {method}")
        console.print(f"DPI: {dpi}\n")
        
        # Validate
        pdf_path = Path(pdf_path)
        validate_file_extension(pdf_path, allowed_extensions=(".pdf",))
        validate_file_size(pdf_path, max_size_mb=settings.max_upload_size_mb)
        
        # Format inference and validation
        output_path = Path(output)
        if format is None:
            # Infer format from file extension
            format = infer_format_from_extension(output_path)
        else:
            # Validate that explicit format matches extension
            validate_format_extension_match(format, output_path)
        
        # Process PDF with hybrid approach
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Initializing...", total=None)
            
            # Initialize model manager (don't pre-load - let strategy manager handle it)
            progress.update(task, description="Initializing...")
            manager = ModelManager(model_configs["models"])
            
            # Determine merge model preference
            merge_model_pref = None if merge_model == "auto" else merge_model

            # Determine which processor to use
            if staged_pipeline:
                # Use staged pipeline processor
                try:
                    from src.preprocessing.staged_pipeline import StagedPipelineProcessor
                except ImportError:
                    console.print("[bold red]Error:[/bold red] Staged pipeline processor not yet implemented", style="red")
                    raise click.Abort()

                from src.preprocessing import PDFHandler
                pdf_handler = PDFHandler(dpi=dpi, min_text_chars=min_text_chars)

                processor = StagedPipelineProcessor(
                    model_manager=manager,
                    pdf_handler=pdf_handler,
                    verbose=verbose,
                    enable_memory_profiling=profile_memory,
                    enable_system_monitoring=not no_monitoring,
                    monitor_interval=monitor_interval,
                    prefer_quality=not prefer_speed
                )
            else:
                # Use existing HybridPDFProcessor (current behavior)
                from src.preprocessing import HybridPDFProcessor, PDFHandler
                pdf_handler = PDFHandler(dpi=dpi, min_text_chars=min_text_chars)
                processor = HybridPDFProcessor(
                    model_manager=manager,
                    pdf_handler=pdf_handler,
                    method=method,
                    force_ocr=force_ocr,
                    min_text_chars=min_text_chars,
                    verbose=verbose,
                    output_format=format,
                    document_context=context,
                    enable_memory_optimization=not no_memory_opt,
                    enable_incremental_mode=incremental,
                    enable_oom_recovery=not no_oom_recovery,
                    enable_spatial_hints=enable_spatial_hints,
                    enable_bbox_annotations=enable_bbox_annotations,
                    disable_crop_mode=disable_crop_mode,
                    enable_memory_profiling=profile_memory,
                    enable_validation=enable_validation,
                    merge_model_preference=merge_model_pref,
                    prefer_quality=not prefer_speed,
                    gpu_strategy=gpu_strategy,
                    enable_checkpointing=not no_checkpointing,
                    enable_system_monitoring=not no_monitoring,
                    monitor_interval=monitor_interval
                )
            
            # Process PDF (with or without calibration)
            if staged_pipeline:
                # Staged pipeline mode - output is required
                if not output:
                    console.print("[bold red]Error:[/bold red] --output/-o required for staged pipeline mode", style="red")
                    raise click.Abort()

                # Ensure output directory exists
                output_path = Path(output)
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Process with staged pipeline
                progress.update(task, description="Processing with staged pipeline...")
                results = processor.process_pdf(
                    pdf_path=pdf_path,
                    output_path=output_path,
                    max_pages=max_pages,
                    dpi=dpi,
                    output_format=format,
                    resume=not no_resume
                )
            elif enable_calibration:
                from src.api.calibration_service import CalibrationConfig
                from src.cli.calibration_ui import CLICalibrationInterface

                config = CalibrationConfig(
                    num_calibration_pages=calibration_pages,
                    require_approval=not skip_approval
                )

                # Create approval callback if needed
                approval_callback = None
                if not skip_approval:
                    cli_interface = CLICalibrationInterface(console)
                    def approval_callback(calibration):
                        cli_interface.display_calibration_results(calibration)
                        return cli_interface.request_approval(calibration)

                # Process with calibration
                progress.update(task, description="Processing with calibration...")
                results = processor.process_pdf_with_calibration(
                    pdf_path,
                    config,
                    approval_callback,
                    max_pages=max_pages,
                    dpi=dpi
                )
            else:
                # Original processing with checkpointing and monitoring
                progress.update(task, description="Processing pages...")

                # Ensure output directory exists
                output_path = Path(output)
                output_path.parent.mkdir(parents=True, exist_ok=True)

                results = processor.process_pdf(
                    pdf_path,
                    max_pages=max_pages,
                    dpi=dpi,
                    output_path=output_path,
                    resume=not no_resume
                )

            progress.update(task, description="Done!", completed=True)

        # Handle output and display summary based on processing mode
        if staged_pipeline:
            # Staged pipeline returns a dict with summary stats
            # Output is written incrementally during processing
            console.print(f"\n[bold green]✓ PDF Processing Complete[/bold green]")
            console.print(f"Results saved to: {output}\n")

            console.print("[bold]Processing Summary:[/bold]")
            console.print(f"  Total pages: {results['total_pages']}")
            console.print(f"  Total time: {results['total_time']:.2f}s")
            console.print(f"  Avg per page: {results['total_time']/results['total_pages']:.2f}s")

            # Display stage-specific stats if available
            if 'ocr_time' in results:
                console.print(f"\n[bold]Stage 1 (OCR):[/bold]")
                console.print(f"  Time: {results['ocr_time']:.2f}s")
                console.print(f"  Avg: {results['ocr_time']/results['total_pages']:.2f}s per page")

            if 'merge_time' in results:
                console.print(f"\n[bold]Stage 2 (Merge):[/bold]")
                console.print(f"  Time: {results['merge_time']:.2f}s")
                console.print(f"  Avg: {results['merge_time']/results['total_pages']:.2f}s per page")
        else:
            # Note: With checkpointing enabled, output is written incrementally during processing
            # This section only runs if checkpointing is disabled or for calibration mode
            if no_checkpointing or enable_calibration:
                # Format output with metadata in HTML comments (invisible but parseable)
                # HTML comments are not displayed in rendered markdown but preserve metadata
                output_text = []

                for result in results:
                    # Create metadata comment with page info
                    # Format: <!-- Page N | Method: METHOD | Time: Xs | Chars: N -->
                    char_count = len(result.text) if result.text else 0
                    metadata = (
                        f"<!-- Page {result.page_num} | "
                        f"Method: {result.method.upper()} | "
                        f"Time: {result.processing_time:.2f}s | "
                        f"Chars: {char_count} -->"
                    )
                    output_text.append(metadata)

                    # Add the actual text content
                    text_to_add = result.text if result.text else ""
                    if text_to_add:
                        output_text.append(text_to_add)
                        # Add blank line between pages for readability
                        output_text.append("")

                # Save results
                output_path = Path(output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text("\n".join(output_text), encoding="utf-8")

            # Display summary
            console.print(f"\n[bold green]✓ PDF Processing Complete[/bold green]")
            console.print(f"Results saved to: {output}\n")

            # Processing summary (always shown)
            console.print("[bold]Processing Summary:[/bold]")
            console.print(f"  Total pages: {len(results)}")

            # Count by method
            method_counts = {}
            for result in results:
                method_counts[result.method] = method_counts.get(result.method, 0) + 1

            for method_name, count in method_counts.items():
                console.print(f"  {method_name.capitalize()}: {count} pages")

            total_time = sum(r.processing_time for r in results)
            console.print(f"  Total time: {total_time:.2f}s")
            console.print(f"  Avg per page: {total_time/len(results):.2f}s")
        
        # Clean up
        manager.unload_all()
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}", style="red")
        raise click.Abort()


@cli.command()
def models():
    """List available models and their configurations."""
    try:
        settings = get_settings()
        model_configs = settings.load_model_configs()
        
        console.print("[bold blue]Available OCR Models[/bold blue]\n")
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Model", style="cyan", width=20)
        table.add_column("VRAM", style="green", width=12)
        table.add_column("Load Time", style="yellow", width=15)
        table.add_column("Description", style="white", width=40)
        
        for name, config in model_configs["models"].items():
            table.add_row(
                name,
                config.get("vram_requirement", "N/A"),
                config.get("load_time", "N/A"),
                config.get("description", "No description"),
            )
        
        console.print(table)
        
        # Show default strategy
        console.print("\n[bold]Default Selection Strategy:[/bold]")
        strategy = model_configs.get("default_strategy", {})
        for key, value in strategy.items():
            console.print(f"  • {key.capitalize()}: [cyan]{value}[/cyan]")
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}", style="red")
        raise click.Abort()


@cli.command()
def gpu():
    """Show GPU information and memory usage."""
    try:
        console.print("[bold blue]GPU Information[/bold blue]\n")
        
        info = get_gpu_info()
        
        if not info["cuda_available"]:
            console.print("[yellow]CUDA is not available on this system[/yellow]")
            return
        
        # Summary
        console.print(f"[bold]CUDA Version:[/bold] {info['cuda_version']}")
        console.print(f"[bold]Device Count:[/bold] {info['device_count']}")
        console.print(f"[bold]Total Memory:[/bold] {info['total_memory_gb']:.2f} GB")
        console.print(f"[bold]Total Allocated:[/bold] {info['total_allocated_gb']:.2f} GB ({info['overall_utilization_percent']}%)")
        console.print(f"[bold]Total Free:[/bold] {info['total_free_gb']:.2f} GB\n")
        
        # Per-device table
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", style="cyan", width=5)
        table.add_column("Name", style="green", width=30)
        table.add_column("Compute", style="yellow", width=10)
        table.add_column("Memory", style="white", width=25)
        table.add_column("Utilization", style="blue", width=15)
        
        for device in info["devices"]:
            memory_str = f"{device['allocated_gb']:.2f} / {device['total_memory_gb']:.2f} GB"
            util_str = f"{device['utilization_percent']}%"
            
            table.add_row(
                str(device["id"]),
                device["name"],
                device["compute_capability"],
                memory_str,
                util_str,
            )
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}", style="red")
        raise click.Abort()


@cli.command()
def info():
    """Show system and environment information."""
    import torch
    import transformers
    
    console.print("[bold blue]OCR Service Information[/bold blue]\n")
    
    # Software versions
    console.print("[bold]Software Versions:[/bold]")
    console.print(f"  Python: {sys.version.split()[0]}")
    console.print(f"  PyTorch: {torch.__version__}")
    console.print(f"  Transformers: {transformers.__version__}")
    
    try:
        import flash_attn
        console.print(f"  Flash-Attention: {flash_attn.__version__}")
    except ImportError:
        console.print("  Flash-Attention: [yellow]Not installed[/yellow]")
    
    # GPU info
    console.print(f"\n[bold]CUDA Available:[/bold] {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        console.print(f"[bold]CUDA Version:[/bold] {torch.version.cuda}")
        console.print(f"[bold]GPU Count:[/bold] {torch.cuda.device_count()}")
    
    # Settings
    settings = get_settings()
    console.print(f"\n[bold]Configuration:[/bold]")
    console.print(f"  Default Model: {settings.default_model}")
    console.print(f"  Max Image Size: {settings.max_image_size}px")
    console.print(f"  Max Upload Size: {settings.max_upload_size_mb}MB")
    console.print(f"  Cache Enabled: {settings.enable_caching}")


@cli.command()
@click.option(
    '--models',
    multiple=True,
    default=['deepseek-ocr', 'qwen3-vl-2b', 'qwen3-vl-4b', 'qwen3-vl-8b'],
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
def profile(models, dpi, output, quick, verbose):
    """
    Run GPU memory profiling across model configurations.

    This command measures actual GPU VRAM consumption for different
    model configurations and compares against calculated forecasts.
    Results are saved in JSON, Markdown, and CSV formats.

    Examples:
      ocr profile --quick
      ocr profile --models deepseek-ocr --dpi 300 600
      ocr profile --output my_results/
    """
    import sys
    from pathlib import Path

    # Import and run the profiling script
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

    from tools.profile_gpu_memory import main as profile_main

    # Call the main function with the appropriate context
    import click.testing
    runner = click.testing.CliRunner()

    args = []
    for model in models:
        args.extend(['--models', model])
    for dpi_val in dpi:
        args.extend(['--dpi', str(dpi_val)])
    args.extend(['--output', str(output)])
    if quick:
        args.append('--quick')
    if not verbose:
        args.append('--quiet')

    # Import the profiling command
    from tools.profile_gpu_memory import main as profiling_main

    # Create a context and invoke
    ctx = click.Context(profile_main)
    ctx.params = {
        'models': models,
        'dpi': dpi,
        'output': output,
        'quick': quick,
        'verbose': verbose
    }

    try:
        profiling_main.invoke(ctx)
    except SystemExit:
        pass  # Normal exit from Click command


@cli.command()
@click.option(
    '--detailed',
    is_flag=True,
    help='Show detailed per-model breakdown'
)
@click.option(
    '--model',
    default=None,
    help='Filter by specific model name'
)
def memory_report(detailed, model):
    """
    Display memory profiling statistics and recommendations.

    Shows aggregate statistics from the profile database including:
    - Total number of profiles collected
    - Average forecast error percentage
    - Number of underestimated/overestimated configurations
    - Tuning recommendations for memory multipliers

    Examples:
      ocr memory-report
      ocr memory-report --detailed
      ocr memory-report --model deepseek-ocr
    """
    from src.utils.memory_profiler import ProfileAnalyzer

    console.print("[bold blue]GPU Memory Profile Report[/bold blue]\n")

    try:
        analyzer = ProfileAnalyzer()
        db = analyzer.db

        # Database statistics
        stats = db.get_stats()

        if stats['total_profiles'] == 0:
            console.print("[yellow]No profiles found. Run 'ocr profile' to collect baseline data.[/yellow]")
            return

        console.print(f"[bold]Database Statistics:[/bold]")
        console.print(f"  Total Profiles: {stats['total_profiles']}")
        console.print(f"  Models: {', '.join(stats['models'])}")
        console.print(f"  DPI Settings: {', '.join(map(str, stats['dpi_settings']))}")

        if stats['date_range']:
            console.print(f"  Date Range: {stats['date_range']['oldest'][:10]} to {stats['date_range']['newest'][:10]}")

        # Error statistics
        error_stats = analyzer.calculate_error_stats()

        console.print(f"\n[bold]Forecast Accuracy:[/bold]")
        console.print(f"  Average Error: {error_stats['avg_error_pct']:.1f}%")
        console.print(f"  Max Error: {error_stats['max_error_pct']:.1f}%")
        console.print(f"  Min Error: {error_stats['min_error_pct']:.1f}%")
        console.print(f"  Std Deviation: {error_stats.get('std_dev_pct', 0):.1f}%")

        # Problem counts
        if error_stats['underestimated_count'] > 0:
            console.print(f"\n[bold red]⚠️  Underestimations (>5%):[/bold red] {error_stats['underestimated_count']}")
        if error_stats['overestimated_count'] > 0:
            console.print(f"[bold yellow]ℹ️  Overestimations (>5%):[/bold yellow] {error_stats['overestimated_count']}")

        # Recommendations
        console.print(f"\n[bold]Recommendations:[/bold]")
        recommendations = analyzer.generate_tuning_recommendations()
        for rec in recommendations:
            console.print(f"  {rec}")

        # Detailed breakdown
        if detailed:
            console.print(f"\n[bold]Per-Model Breakdown:[/bold]")
            breakdown = analyzer.get_model_breakdown()

            # Filter by model if specified
            if model:
                breakdown = {k: v for k, v in breakdown.items() if model.lower() in k.lower()}

            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Model", style="cyan")
            table.add_column("Profiles", justify="right")
            table.add_column("Avg Peak (GB)", justify="right")
            table.add_column("Max Peak (GB)", justify="right")
            table.add_column("Min Peak (GB)", justify="right")

            for model_name, data in breakdown.items():
                table.add_row(
                    model_name,
                    str(data['count']),
                    f"{data['avg_peak_gb']:.2f}",
                    f"{data['max_peak_gb']:.2f}",
                    f"{data['min_peak_gb']:.2f}"
                )

            console.print(table)

        console.print(f"\n[dim]Database: .memory_profiles.json[/dim]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        if detailed:
            import traceback
            console.print(traceback.format_exc())


if __name__ == "__main__":
    cli()

