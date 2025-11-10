# Checkpoint and System Monitoring Implementation

## Summary

Implemented comprehensive checkpoint/resume and system monitoring capabilities for the PDF processing pipeline to prevent data loss from crashes and enable better diagnostics.

## Problem

The original system had two major issues:
1. **No crash recovery**: Processing crashed ~17 minutes into parsing 173-page documents, losing all progress
2. **No diagnostic data**: Couldn't determine why the system crashed (GPU memory? System RAM? Thermal issues?)

## Solution

Implemented two complementary systems:

### 1. Checkpoint/Resume System
- **Incremental output writing**: Pages written to disk immediately after processing
- **Resume capability**: Can restart from last completed page after crash
- **Atomic checkpoints**: Checkpoint state saved after each page

### 2. System Monitoring
- **Real-time metrics**: GPU memory, CPU, RAM, temperature tracked every 30s
- **Background thread**: Non-blocking monitoring during processing
- **JSON Lines format**: Easy to parse and analyze crash conditions

---

## Files Created

### 1. `/src/preprocessing/checkpoint_manager.py`
**Purpose**: Manages checkpoint state for resumable processing

**Key Features**:
- Save checkpoint after each page
- Load and validate existing checkpoints
- Atomic writes (temp file + rename)
- Automatic cleanup on successful completion

**Checkpoint Format** (`.checkpoint.json`):
```json
{
  "pdf_path": "data/input/Bodine-D22.pdf",
  "output_path": "data/output/Bodine-D22-full.md",
  "total_pages": 173,
  "last_completed_page": 14,
  "start_time": "2025-11-07T17:28:00Z",
  "last_update": "2025-11-07T17:35:42Z",
  "processing_params": {
    "dpi": 300,
    "method": "hybrid",
    "merge_model": "qwen2-vl-7b"
  }
}
```

### 2. `/src/utils/system_monitor.py`
**Purpose**: Monitor system resources during processing

**Key Features**:
- Background monitoring thread (configurable interval)
- GPU metrics via pynvml: memory, utilization, temperature
- System metrics: CPU, RAM
- Process metrics: memory, CPU usage
- JSON Lines output format (one JSON object per line)

**System Log Format** (`.syslog.jsonl`):
```json
{
  "timestamp": "2025-11-07T17:35:42Z",
  "page": 15,
  "total_pages": 173,
  "process": {
    "rss_mb": 8234.1,
    "vms_mb": 15432.0,
    "cpu_percent": 104.5
  },
  "system": {
    "ram_available_mb": 12456.2,
    "ram_percent": 45.3,
    "cpu_percent": 55.2
  },
  "gpus": [
    {
      "id": 0,
      "memory_used_mb": 24103.5,
      "memory_total_mb": 24564.0,
      "memory_percent": 98.1,
      "utilization_percent": 98,
      "temperature_c": 78
    },
    {
      "id": 1,
      "memory_used_mb": 17592.3,
      "memory_total_mb": 24564.0,
      "memory_percent": 71.6,
      "utilization_percent": 85,
      "temperature_c": 75
    }
  ]
}
```

---

## Files Modified

### 1. `/src/preprocessing/pdf_pipeline.py`

**Changes**:

#### Added imports:
```python
from .checkpoint_manager import CheckpointManager
from ..utils.system_monitor import SystemMonitor
import logging
```

#### New `__init__` parameters:
- `enable_checkpointing`: Enable checkpoint/resume (default: True)
- `enable_system_monitoring`: Enable resource monitoring (default: True)
- `monitor_interval`: Monitoring interval in seconds (default: 30)

#### New `process_pdf` parameters:
- `output_path`: Required for checkpointing (Path to output file)
- `resume`: Whether to resume from checkpoint (default: True)

#### Key modifications in `process_pdf()`:

1. **Checkpoint initialization** (lines 156-175):
   - Creates CheckpointManager
   - Checks for existing checkpoint
   - Determines start page for resume

2. **System monitor initialization** (lines 177-181):
   - Creates SystemMonitor
   - Starts background monitoring thread

3. **Resume logic** (lines 207-209):
   - Skip already processed pages when resuming

4. **Progress tracking** (lines 211-217):
   - Update monitor with current page
   - Display progress percentage with flush=True

5. **Incremental output writing** (lines 261-266):
   - Write each page immediately after processing
   - Save checkpoint after each page
   - Force flush to disk

6. **Cleanup** (lines 307-316):
   - Stop system monitor
   - Clear checkpoint on successful completion
   - Wrapped in try/finally for safety

#### New helper method:

**`_write_page_result()`** (lines 320-346):
- Writes single page to output file
- Supports append mode for incremental writes
- Adds metadata comments
- Forces flush to disk

### 2. `/src/cli/commands.py`

**Changes**:

#### New CLI options (lines 335-355):
```python
--no-resume            # Disable automatic resume from checkpoint
--no-checkpointing     # Disable checkpoint/resume completely
--no-monitoring        # Disable system resource monitoring
--monitor-interval N   # Monitoring interval in seconds (default: 30)
```

#### Updated processor initialization (lines 467-469):
```python
enable_checkpointing=not no_checkpointing,
enable_system_monitoring=not no_monitoring,
monitor_interval=monitor_interval
```

#### Updated `process_pdf` call (lines 500-513):
```python
# Ensure output directory exists
output_path = Path(output)
output_path.parent.mkdir(parents=True, exist_ok=True)

results = processor.process_pdf(
    pdf_path,
    max_pages=max_pages,
    dpi=dpi,
    output_path=output_path,  # NEW: Required for checkpointing
    resume=not no_resume       # NEW: Resume control
)
```

#### Conditional batch write (lines 517-546):
- Only runs if checkpointing disabled or calibration mode
- Otherwise output already written incrementally

---

## Usage

### Basic Usage (Checkpoint & Monitoring Enabled by Default)

```bash
python -m src.cli.commands pdf input.pdf -o output.md
```

This will:
- Write output incrementally (page by page)
- Save checkpoint after each page
- Monitor system resources every 30s
- Auto-resume if interrupted

### Resume After Crash

Just run the same command again:

```bash
python -m src.cli.commands pdf input.pdf -o output.md
```

Output:
```
Resuming from page 15
Processing page 15/173 (8.7%)... HYBRID (18.23s)
...
```

### Disable Checkpointing

```bash
python -m src.cli.commands pdf input.pdf -o output.md --no-checkpointing
```

### Disable Monitoring

```bash
python -m src.cli.commands pdf input.pdf -o output.md --no-monitoring
```

### Custom Monitoring Interval

```bash
python -m src.cli.commands pdf input.pdf -o output.md --monitor-interval 60
```

### Start from Scratch (Ignore Checkpoint)

```bash
python -m src.cli.commands pdf input.pdf -o output.md --no-resume
```

---

## Output Files

When processing `data/input/Bodine-D22.pdf` to `data/output/Bodine-D22-full.md`:

1. **Main output**: `data/output/Bodine-D22-full.md`
   - Incrementally written (updated after each page)
   - Contains processed text with metadata

2. **Checkpoint**: `data/output/Bodine-D22-full.checkpoint.json`
   - Tracks last completed page
   - Auto-deleted on successful completion
   - Used for resume

3. **System log**: `data/output/Bodine-D22-full.syslog.jsonl`
   - One JSON object per line
   - Metrics logged every 30s (or custom interval)
   - Useful for diagnosing crashes

---

## Crash Diagnostics

After a crash, analyze the system log:

```bash
# View last 10 entries before crash
tail -10 data/output/Bodine-D22-full.syslog.jsonl | jq .

# Check GPU memory trend
cat data/output/Bodine-D22-full.syslog.jsonl | jq -r '[.timestamp, .page, .gpus[0].memory_percent] | @csv'

# Check for RAM exhaustion
cat data/output/Bodine-D22-full.syslog.jsonl | jq -r '[.timestamp, .system.ram_percent] | @csv'

# Check GPU temperatures
cat data/output/Bodine-D22-full.syslog.jsonl | jq -r '[.timestamp, .gpus[0].temperature_c, .gpus[1].temperature_c] | @csv'
```

---

## Testing

Run the test suite:

```bash
python test_checkpoint_system.py
```

Expected output:
```
Testing imports...
✓ CheckpointManager imported successfully
✓ SystemMonitor imported successfully

Testing CheckpointManager...
✓ CheckpointManager initialized
✓ Dummy output file created
✓ Checkpoint saved
✓ Checkpoint loaded successfully
✓ Resume page correct: 6
✓ Checkpoint cleared
✓ Checkpoint properly deleted

Testing SystemMonitor...
✓ SystemMonitor initialized
✓ SystemMonitor started
✓ Progress updated
✓ SystemMonitor stopped
✓ System log created: test_output.syslog.jsonl

==================================================
All tests passed! ✓
==================================================
```

---

## Technical Details

### Checkpoint Validation

Checkpoints are validated on load to ensure safety:
- PDF path must match
- Output path must match
- Output file must exist
- Critical processing params must match (dpi, method, format)

Invalid checkpoints are automatically ignored.

### Incremental Write Safety

- Each page written immediately after processing
- Output flushed to disk after each write (`f.flush()`)
- Append mode used for subsequent pages
- Checkpoint updated after successful write

### System Monitor Thread Safety

- Runs in background daemon thread
- Non-blocking (doesn't slow processing)
- Automatic cleanup on exit
- Handles NVML initialization failures gracefully

### Progress Display

- Shows `Page X/Y (Z.Z%)` format
- Uses `flush=True` to prevent buffering
- ETA could be added based on avg page time

---

## Future Enhancements

1. **ETA calculation**: Show estimated time remaining
2. **Partial page recovery**: Save crop results before merge
3. **Multiple checkpoint strategies**: Every N pages, time-based, size-based
4. **Checkpoint compression**: Compress old checkpoint data
5. **Web UI integration**: Real-time progress visualization
6. **Alert thresholds**: Warn if GPU temp > 85°C or RAM > 90%
7. **Graceful interrupt**: Save checkpoint on Ctrl+C (SIGINT handler)

---

## Benefits

### For Users:
- ✅ No work lost if system crashes
- ✅ Can stop and resume processing anytime
- ✅ Real-time progress visibility
- ✅ Better understanding of system resource usage

### For Debugging:
- ✅ Know exactly where crash occurred (last checkpoint page)
- ✅ See system state leading up to crash
- ✅ Identify if crash was GPU/RAM/thermal related
- ✅ Correlate crashes with specific pages or processing stages

### For Optimization:
- ✅ Analyze resource usage patterns
- ✅ Identify memory leaks (growing RAM over time)
- ✅ Optimize batch sizes based on available resources
- ✅ Tune monitoring intervals for performance

---

## Notes

- System monitoring requires `psutil` (already in requirements)
- GPU monitoring requires `pynvml` (installed with `nvidia-ml-py`)
- Checkpoint files are small (~500 bytes each)
- System logs grow ~200 bytes per interval (30s default = 24KB/hour)
- All files auto-cleanup on successful completion
