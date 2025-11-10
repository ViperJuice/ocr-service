# Resource Management and Crash Prevention Specification

**Version:** 1.0
**Date:** 2025-11-09
**Status:** Phases 1-3 Implemented, Testing in Progress

---

## Executive Summary

This specification addresses the system lockup issue discovered during batch processing testing, where multiple concurrent jobs attempted to load GPU models simultaneously, causing system RAM exhaustion and requiring a forced reboot.

**Key Finding:** The codebase already uses industry-standard Hugging Face libraries for GPU memory management (`device_map="auto"`, `max_memory`). The crash was caused by **application-level job concurrency** - multiple jobs running in parallel without coordination, each successfully loading models that collectively exceeded available resources.

**Solution Approach:** Add minimal job-level resource tracking (~40 lines of code) while continuing to leverage existing Hugging Face and PyTorch functionality for all model loading and GPU management.

### PRIMARY DESIGN PRINCIPLE: Quality Over Speed

**CRITICAL**: This system prioritizes precision and capability over throughput. The guiding principle is:

> **Serial execution at maximum quality is ALWAYS preferred over parallel execution at reduced quality.**

**What This Means in Practice:**
- ✅ If system can run Tier 1 (maximum quality), ALL jobs run at Tier 1, queued serially
- ❌ NEVER reduce quality to enable concurrent execution
- ✅ Quality tiers 2-5 exist ONLY for systems that cannot physically run Tier 1 (e.g., 16GB GPU)
- ❌ On capable systems (like current 2×24GB setup), quality tiers 2-5 are NOT USED
- ✅ Jobs wait in queue rather than run at reduced quality
- ✅ Optimization goal: **Maximum precision and capability**, NOT speed

**Example on Current System (2×24GB RTX 4090):**
- Job 1 submitted → Starts at Tier 1 (100% quality, 32GB)
- Job 2 submitted → Waits in queue for Job 1 to complete
- Job 2 starts → Runs at Tier 1 (100% quality, 32GB)
- Result: Both jobs at maximum quality, serial execution

---

## Problem Statement

### Root Cause Analysis

**System Crash Event (Nov 7, 2025):**
```
kernel: __vm_enough_memory: pid: 61142, comm: python3, not enough memory for the allocation
[Multiple consecutive allocation failures]
systemd-journald: File corrupted or uncleanly shut down
```

**Analysis:**
1. `max_concurrent_jobs=2` setting exists but is **not enforced**
2. Multiple jobs started simultaneously without resource coordination
3. Each job loaded DeepSeek-OCR model with crop_mode (~14GB VRAM each)
4. 2-3 jobs × 14GB = 28-42GB demand exceeded single GPU capacity
5. System RAM exhaustion led to kernel allocation failure and system freeze

### Current State

**What's Working (Leveraging Existing Libraries):**
- ✅ Hugging Face `device_map="auto"` for multi-GPU placement
- ✅ Hugging Face `max_memory` for per-GPU limits during model loading
- ✅ bitsandbytes quantization (int8/int4) integration
- ✅ PyTorch CUDA memory monitoring and cache management
- ✅ Model caching within single job instances

**What's Missing (Application-Level Logic):**
- ❌ No enforcement of `max_concurrent_jobs` limit
- ❌ No tracking of VRAM usage across concurrent jobs
- ❌ No job queueing when resources are full
- ❌ No graceful degradation when resources are constrained

---

## Design Principles

### Core Tenets

1. **Leverage Existing Libraries**
   - Continue using Hugging Face for all model loading and GPU management
   - Use PyTorch for memory monitoring and optimization
   - Only build minimal application-level coordination logic

2. **Quality Over Speed (PRIMARY PRINCIPLE)**
   - **NEVER compromise quality for parallelism**
   - **Serial execution at maximum quality is ALWAYS preferred over parallel execution at reduced quality**
   - If concurrent jobs cannot run at Tier 1 (maximum quality), queue them instead
   - Only use quality degradation tiers as a fallback when even serial execution would fail (e.g., system lacks minimum VRAM)
   - Optimization goal: **Precision and capability first, speed second**

3. **Quality-First Resource Allocation**
   - Always try full-capability models first (crop_mode=true, full resolution, Tier 1)
   - Only reduce quality when single-job execution would fail due to insufficient resources
   - Never reduce quality to enable parallel execution
   - Default behavior: Queue jobs and execute serially at maximum quality

4. **Conservative Degradation (Last Resort Only)**
   - Quality tiers exist ONLY for systems that cannot run Tier 1 even with a single job
   - Example: 16GB GPU that cannot fit Tier 1 (32GB requirement) should use Tier 5
   - Tiers 2-5 are NOT for enabling concurrency on capable systems
   - If system can run Tier 1, ALL jobs should run at Tier 1 (queued if necessary)

5. **Prevent System Crashes**
   - Hard enforcement of concurrency limits via semaphores
   - Pre-flight resource checks before starting jobs
   - Resource reservation system to prevent overcommitment
   - Conservative VRAM estimates with safety margins

6. **Adaptive to System Capabilities**
   - High-end systems (128GB RAM, multi-GPU): Run Tier 1, potentially 2 jobs in parallel IF both can be Tier 1
   - Current system (62GB RAM, 2×RTX 4090): Run Tier 1, single job at a time (queue others)
   - Low-end systems (16GB RAM, single GPU): Run best tier that fits, single job at a time

---

## Architecture Overview

### Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│  JobManager (Enhanced)                                  │
│  - Job queue with priority                              │
│  - Consults GPUResourceTracker before starting          │
│  - Enforces max_concurrent_jobs with Semaphore          │
│  - Quality-tier selection based on available resources  │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  GPUResourceTracker (NEW - ~40 lines)                  │
│  - Tracks VRAM allocation per GPU                       │
│  - Thread-safe acquire/release with Lock                │
│  - Simple dictionary: {gpu_id: used_gb}                 │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  ModelManager (Unchanged - Uses HF)                     │
│  - device_map="auto" for GPU placement                  │
│  - max_memory for per-GPU limits                        │
│  - load_in_8bit/load_in_4bit for quantization          │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  Hugging Face Transformers + Accelerate                │
│  ✅ Automatic multi-GPU sharding                        │
│  ✅ Memory-aware model loading                          │
│  ✅ Quantization via bitsandbytes                       │
│  ✅ Device placement optimization                       │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  PyTorch CUDA (Monitoring Only)                        │
│  ✅ torch.cuda.memory_allocated()                       │
│  ✅ torch.cuda.empty_cache()                            │
│  ✅ torch.amp.autocast() for mixed precision            │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. User submits job
   ↓
2. JobManager receives job → Adds to queue
   ↓
3. Scheduler loop (background thread):
   a. Get next job from queue
   b. Determine system's maximum quality tier (check if Tier 1 can EVER run)
   c. Check GPUResourceTracker: enough VRAM for maximum quality tier?
      - YES → Acquire resources, start job at maximum quality
      - NO (resources in use) → Wait in queue, do NOT degrade quality
      - NO (system incapable) → Determine best tier system can support, use that tier
   d. CRITICAL: Never trade quality for concurrency
   ↓
4. Job processing:
   a. Model loading via HuggingFace (device_map, max_memory)
   b. Inference via StagedPipelineProcessor
   c. Progress updates via ProgressEmitter
   ↓
5. Job completion:
   a. Release resources via GPUResourceTracker
   b. Unload model (if no other jobs using it)
   c. Trigger next job in queue
```

---

## Quality Degradation Tiers

### Tier Definitions

**IMPORTANT**: Quality tiers exist ONLY for systems with insufficient hardware to run Tier 1, NOT to enable parallel execution. The system determines the maximum tier the hardware can support (system capability tier), then runs ALL jobs at that tier serially.

**Tier Selection Logic**:
1. At startup, determine system's maximum capability tier (likely Tier 1 for most systems)
2. ALL jobs run at this tier, queued serially
3. Lower tiers are ONLY used if system hardware cannot support Tier 1 even for a single job
4. Example: 16GB GPU → Use Tier 5 for all jobs (serially)
5. Example: 2×24GB GPUs → Use Tier 1 for all jobs (serially, queue as needed)

Each tier represents a configuration that balances quality vs resource usage:

#### Tier 1: Maximum Quality (100 points)
```yaml
quality_score: 100
ocr_model: deepseek-ocr
merge_model: qwen3-vl-8b
crop_mode: true
resolution_mode: gundam (300 DPI)
quantization: none
gpu_strategy: dual_gpu
estimated_vram:
  gpu_0: 14GB  # DeepSeek-OCR with crops
  gpu_1: 19GB  # Qwen3-VL-8B
total_vram: 33GB
use_case: High-end systems, single job at a time
```

#### Tier 1.5: Intermediate with Crops (92 points)
```yaml
quality_score: 92
ocr_model: deepseek-ocr
merge_model: qwen3-vl-4b
crop_mode: true
resolution_mode: gundam (300 DPI)
quantization: none
gpu_strategy: dual_gpu
estimated_vram:
  gpu_0: 14GB  # DeepSeek-OCR with crops
  gpu_1: 13GB  # Qwen3-VL-4B
total_vram: 27GB
use_case: Better quality than 2B, fits on 2×16GB GPUs
quality_impact: Excellent quality, intermediate between 8B and 2B
```

#### Tier 2: Disable Crop Mode with 8B (85 points)
```yaml
quality_score: 85
ocr_model: deepseek-ocr
merge_model: qwen3-vl-8b
crop_mode: false
resolution_mode: gundam (300 DPI)
quantization: none
gpu_strategy: dual_gpu
estimated_vram:
  gpu_0: 10GB  # DeepSeek-OCR without crops
  gpu_1: 19GB  # Qwen3-VL-8B
total_vram: 29GB
use_case: Current system, allows 2 jobs if staggered
quality_impact: Minor reduction in table/complex layout accuracy
```

#### Tier 2.5: 4B without Crops (82 points)
```yaml
quality_score: 82
ocr_model: deepseek-ocr
merge_model: qwen3-vl-4b
crop_mode: false
resolution_mode: gundam (300 DPI)
quantization: none
gpu_strategy: dual_gpu
estimated_vram:
  gpu_0: 10GB  # DeepSeek-OCR without crops
  gpu_1: 13GB  # Qwen3-VL-4B
total_vram: 23GB
use_case: Medium systems, good balance
quality_impact: Minimal reduction, good quality
```

#### Tier 3: Smaller Merge Model (80 points)
```yaml
quality_score: 80
ocr_model: deepseek-ocr
merge_model: qwen3-vl-2b  # Smaller model
crop_mode: true
resolution_mode: gundam (300 DPI)
quantization: none
gpu_strategy: dual_gpu
estimated_vram:
  gpu_0: 14GB  # DeepSeek-OCR with crops
  gpu_1: 9GB   # Qwen3-VL-2B
total_vram: 23GB
use_case: Memory-constrained dual-GPU systems
quality_impact: Reduced merge quality, may miss some cross-page context
```

#### Tier 4: Both Optimizations (70 points)
```yaml
quality_score: 70
ocr_model: deepseek-ocr
merge_model: qwen3-vl-2b
crop_mode: false
resolution_mode: gundam (300 DPI)
quantization: none
gpu_strategy: single_gpu  # Can fit on one GPU
estimated_vram:
  gpu_0: 19GB  # Both models sequentially (slightly more than before)
total_vram: 19GB
use_case: Single GPU systems or parallel jobs on dual-GPU
quality_impact: Moderate - both crop and merge quality reduced
```

#### Tier 5: Quantized Models (60 points)
```yaml
quality_score: 60
ocr_model: deepseek-ocr
merge_model: qwen3-vl-8b
crop_mode: false
resolution_mode: base (150 DPI)
quantization: int8  # Reduce model weights by ~50%
gpu_strategy: single_gpu
estimated_vram:
  gpu_0: 9GB
total_vram: 9GB
use_case: Low-end systems, maximum parallelism
quality_impact: Noticeable quality reduction, suitable for simple documents
```

#### Tier 6: Failure
```
If even Tier 5 doesn't fit, fail with clear error:
"Insufficient GPU memory. Available: {X}GB, Minimum required: 9GB"
```

### Quality Impact Summary

| Tier | Quality | Use Case | Concurrency Mode |
|------|---------|----------|------------------|
| 1    | 100%    | Systems with 2×24GB GPUs (MOST SYSTEMS) | Serial at maximum quality |
| 2    | 85%     | NOT USED (quality > speed principle) | N/A |
| 3    | 80%     | NOT USED (quality > speed principle) | N/A |
| 4    | 70%     | NOT USED (quality > speed principle) | N/A |
| 5    | 60%     | Systems with <16GB GPU only | Serial at reduced quality |

**CRITICAL CLARIFICATION**: Tiers 2-4 are **NOT** for enabling concurrency. They exist only for systems that physically cannot run Tier 1. On systems capable of Tier 1 (like current 2×24GB setup), ALL jobs run at Tier 1 in serial/queued mode.

---

## Concurrency Policy (Quality Over Speed)

### Behavior on Current System (2×24GB RTX 4090)

**Scenario 1: Single Job Submitted**
```
Action: Start immediately at Tier 1 (crop_mode=true, dual GPU, 32GB total)
Result: Maximum quality, full capabilities
Queue: Empty
```

**Scenario 2: Two Jobs Submitted Simultaneously**
```
Action:
  - Job 1: Start at Tier 1 (uses both GPUs, 32GB)
  - Job 2: Queue (wait for Job 1 to complete)
Result:
  - Job 1: Maximum quality (Tier 1)
  - Job 2: Maximum quality (Tier 1) after waiting
  - NEVER downgrade Job 2 to Tier 4 to run concurrently
Queue: Job 2 waiting
Rationale: Serial execution at 100% quality > parallel at 70% quality
```

**Scenario 3: User Explicitly Requests Parallel Execution**
```
Action: Check if both jobs can run at Tier 1 simultaneously
  - Current system: 2 jobs × 32GB = 64GB > 48GB available
  - Answer: NO
  - Behavior: Reject parallel request OR queue second job
Result: Maintain quality, do not compromise
```

### Behavior on Low-End System (1×16GB GPU)

**Scenario 1: Single Job Submitted**
```
System Capability Check:
  - Tier 1 requires 32GB (dual GPU) → Not possible (only 1 GPU)
  - Tier 5 requires 8GB (single GPU) → Fits!

Action: Start at Tier 5 (best tier system can support)
Result: Reduced quality (60%), but consistent for all jobs
```

**Scenario 2: Two Jobs on Low-End System**
```
Action:
  - Job 1: Start at Tier 5 (8GB)
  - Job 2: Queue (wait for Job 1)
Result: Both at Tier 5, serial execution
Rationale: System's maximum capability is Tier 5, use it consistently
```

### When is Parallel Execution Allowed?

**Only when BOTH conditions are met:**
1. System has sufficient resources for multiple jobs at maximum quality tier simultaneously
2. Example: 4×24GB GPUs could run 2 Tier 1 jobs in parallel (2 jobs × 32GB = 64GB < 96GB available)

**Current system (2×24GB) verdict**: Serial execution only (1 job × 32GB fits, 2 jobs × 32GB does not)

---

## Implementation Details

### 1. GPUResourceTracker

**File:** `src/api/services/gpu_resource_tracker.py` (NEW)

**Purpose:** Track VRAM allocation across concurrent jobs with thread-safe acquire/release.

**Interface:**
```python
class GPUResourceTracker:
    """
    Lightweight VRAM tracking for job scheduling.

    Does NOT replace HuggingFace's device_map or max_memory.
    Only tracks application-level job allocations.
    """

    def __init__(self, gpu_capacities_gb: Dict[int, float]):
        """
        Args:
            gpu_capacities_gb: {gpu_id: usable_vram_gb}
                Example: {0: 22.0, 1: 22.0}  # 24GB - 2GB overhead
        """

    def can_allocate(self, vram_requirements: Dict[int, float]) -> bool:
        """
        Check if VRAM is available without blocking.

        Args:
            vram_requirements: {gpu_id: gb_needed}

        Returns:
            True if all GPUs have sufficient free VRAM
        """

    def acquire(self, vram_requirements: Dict[int, float], job_id: str) -> bool:
        """
        Reserve VRAM for a job. Non-blocking.

        Returns:
            True if reservation successful, False if insufficient
        """

    def release(self, job_id: str):
        """Release all VRAM reserved by a job."""

    def get_status(self) -> Dict:
        """Get current VRAM usage per GPU."""
```

**Key Implementation Notes:**
- Uses `threading.Lock` per GPU for thread-safety
- Tracks allocations in simple dict: `{gpu_id: {job_id: vram_gb}}`
- Does NOT interact with CUDA directly - pure accounting
- Total code: ~40-50 lines

### 2. JobManager Enhancements

**File:** `src/api/services/job_manager.py` (MODIFY)

**Changes:**

1. **Add GPUResourceTracker integration:**
```python
def __init__(
    self,
    processing_directory: str,
    output_directory: str,
    max_concurrent_jobs: int = 2,
    gpu_tracker: Optional[GPUResourceTracker] = None  # NEW
):
    # ... existing init ...
    self.gpu_tracker = gpu_tracker
    self.job_semaphore = threading.Semaphore(max_concurrent_jobs)  # NEW: Enforce limit
```

2. **Add quality tier selection:**
```python
def _select_quality_tier(
    self,
    job: Job,
    available_gpus: List[int]
) -> Dict[str, Any]:
    """
    Select best quality tier that fits in available VRAM.

    Returns:
        {
            'tier': 1-5,
            'quality_score': 100-60,
            'model_config': {...},
            'vram_requirements': {gpu_id: gb}
        }
    """
    # Load tier definitions from config
    tiers = self._load_quality_tiers()

    # Try tiers in order (best quality first)
    for tier in tiers:
        if self.gpu_tracker.can_allocate(tier['vram_requirements']):
            return tier

    # No tier fits
    raise InsufficientResourcesError(f"Minimum VRAM required: 8GB")
```

3. **Add resource reservation before job start:**
```python
def start_job(self, job_id: str, ...):
    # Select quality tier
    tier = self._select_quality_tier(job, available_gpus)

    # Reserve resources (blocks until available or timeout)
    if not self.gpu_tracker.acquire(tier['vram_requirements'], job_id):
        # Queue job or return 503
        raise ResourceUnavailableError("GPU resources unavailable")

    try:
        # Acquire semaphore slot
        self.job_semaphore.acquire()

        # Start job thread
        thread = threading.Thread(
            target=self._process_job_async,
            args=(job, tier, ...)
        )
        thread.start()
    except Exception:
        # Release resources on failure
        self.gpu_tracker.release(job_id)
        raise
```

4. **Add resource release after job completion:**
```python
def _process_job_async(self, job, tier, ...):
    try:
        # ... existing job processing ...
        pass
    finally:
        # Always release resources
        self.gpu_tracker.release(job.job_id)
        self.job_semaphore.release()
```

### 3. Model Config Enhancements

**File:** `config/model_configs.yaml` (MODIFY)

**Add VRAM estimation metadata:**

```yaml
deepseek-ocr:
  config:
    # Existing HuggingFace config (UNCHANGED)
    device_map: "auto"
    max_memory:
      0: "22GB"
      1: "22GB"
    low_cpu_mem_usage: true

  # NEW: VRAM estimation for job scheduling
  vram_estimates:
    base_model_gb: 6.0
    inference_overhead:
      300dpi_with_crops: 7.5
      300dpi_no_crops: 3.5
      150dpi_with_crops: 4.0
      150dpi_no_crops: 2.0
    quantization_reduction:
      int8: 0.5  # 50% reduction
      int4: 0.75 # 75% reduction

qwen2-vl-7b:
  config:
    device_map: "auto"
    max_memory:
      0: "22GB"
      1: "22GB"
    low_cpu_mem_usage: true

  vram_estimates:
    base_model_gb: 14.0
    inference_overhead:
      300dpi: 3.75
      150dpi: 2.0
    quantization_reduction:
      int8: 0.5
      int4: 0.75
```

### 4. Quality Tier Config

**File:** `config/quality_tiers.yaml` (NEW)

```yaml
quality_tiers:
  - tier: 1
    name: "Maximum Quality"
    quality_score: 100
    config:
      ocr_model: deepseek-ocr
      merge_model: qwen2-vl-7b
      crop_mode: true
      resolution_mode: gundam
      dpi: 300
      quantization: null
    vram_requirements:
      0: 14.0  # DeepSeek-OCR
      1: 18.0  # Qwen2-VL-7B
    strategy: dual_gpu

  - tier: 2
    name: "Disable Crop Mode"
    quality_score: 85
    config:
      ocr_model: deepseek-ocr
      merge_model: qwen2-vl-7b
      crop_mode: false
      resolution_mode: gundam
      dpi: 300
      quantization: null
    vram_requirements:
      0: 10.0
      1: 18.0
    strategy: dual_gpu

  # ... tiers 3-5 ...
```

### 5. Main.py Integration

**File:** `src/api/main.py` (MODIFY)

```python
from .services import (
    FileManager, PromptManager, JobManager,
    BatchManager, ProgressEmitter,
    GPUResourceTracker  # NEW
)

# Global service instances
gpu_tracker: GPUResourceTracker = None  # NEW

@asynccontextmanager
async def lifespan(app: FastAPI):
    global file_manager, prompt_manager, job_manager, gpu_tracker, ...

    # Initialize GPU resource tracker
    gpu_tracker = GPUResourceTracker({
        0: 22.0,  # RTX 4090: 24GB - 2GB overhead
        1: 22.0
    })

    # Initialize JobManager with resource tracker
    job_manager = JobManager(
        processing_directory=settings.api_processing_directory,
        output_directory=settings.api_output_directory,
        max_concurrent_jobs=2,
        gpu_tracker=gpu_tracker  # NEW
    )

    # ... rest unchanged ...
```

---

## Testing Strategy

### Test Scenarios

#### Test 1: Single Job (Full Quality)
```
Input: Submit 1 job
Expected: Uses Tier 1 (full quality, dual GPU)
Validation:
  - GPUResourceTracker shows 14GB on GPU 0, 18GB on GPU 1
  - Job completes with quality_score=100
  - Resources released after completion
```

#### Test 2: Concurrent Jobs (Resource Contention)
```
Input: Submit 2 jobs simultaneously
Expected:
  - Job 1: Starts immediately with Tier 1 (32GB total)
  - Job 2: Waits in queue (insufficient VRAM)
  - After Job 1 completes: Job 2 starts with Tier 1
Validation:
  - Only 1 job active at a time
  - No system OOM
  - Both jobs complete at full quality
```

#### Test 3: Graceful Degradation
```
Input: Submit 2 jobs with tier override allowing degradation
Expected:
  - Job 1: Tier 1 (32GB)
  - Job 2: Tier 4 (17GB on GPU 0, fits in remaining space)
Validation:
  - 2 jobs running concurrently
  - Job 1: quality_score=100
  - Job 2: quality_score=70
  - Total VRAM < capacity
```

#### Test 4: Resource Exhaustion
```
Input: Mock system with 16GB total VRAM, submit job
Expected:
  - Tier 1-4 rejected (insufficient VRAM)
  - Tier 5 selected (8GB)
  - Job completes with quality_score=60
Validation:
  - No crash
  - Clear logging of tier selection
```

#### Test 5: Batch Processing
```
Input: Batch with 3 documents
Expected:
  - Documents process serially (default)
  - Same model instance reused across documents
  - VRAM allocated once, released after last document
Validation:
  - No duplicate model loading
  - Efficient resource usage
```

### Test Files

#### Unit Tests
- `tests/unit/test_gpu_resource_tracker.py`
  - Test acquire/release mechanics
  - Test thread safety with concurrent access
  - Test edge cases (over-allocation, double-release)

- `tests/unit/test_quality_tier_selection.py`
  - Test tier selection logic
  - Test tier ordering (best-first)
  - Test failure when no tier fits

#### Integration Tests
- `tests/integration/test_concurrent_jobs.py`
  - Test 2+ jobs competing for resources
  - Test queueing behavior
  - Test resource release on job failure

- `tests/integration/test_batch_processing_resources.py`
  - Test batch with multiple documents
  - Test resource tracking across batch lifecycle

### Mock Testing (No GPU Required)

Create mock GPU tracker for CI/CD:
```python
class MockGPUResourceTracker:
    """Mock for testing without GPU."""
    def __init__(self, capacities):
        self.capacities = capacities
        self.allocations = {gpu_id: {} for gpu_id in capacities}

    # ... same interface as real GPUResourceTracker ...
```

---

## Monitoring and Observability

### Logging

Add structured logging at key points:

```python
# Job start
logger.info(
    f"Starting job {job_id}",
    extra={
        "job_id": job_id,
        "quality_tier": tier['tier'],
        "quality_score": tier['quality_score'],
        "vram_allocated": tier['vram_requirements'],
        "concurrent_jobs": self._count_active_jobs()
    }
)

# Resource acquisition
logger.debug(
    f"Acquired VRAM for job {job_id}",
    extra={
        "job_id": job_id,
        "vram_requirements": vram_requirements,
        "gpu_status": self.gpu_tracker.get_status()
    }
)

# Tier degradation
logger.warning(
    f"Degraded quality tier for job {job_id}",
    extra={
        "job_id": job_id,
        "attempted_tier": 1,
        "selected_tier": tier['tier'],
        "reason": "insufficient_vram"
    }
)
```

### Metrics

Expose metrics via monitoring endpoint:

```python
@router.get("/api/v1/monitoring/resources")
async def get_resource_status():
    return {
        "gpu_status": gpu_tracker.get_status(),
        "active_jobs": job_manager.count_active_jobs(),
        "queued_jobs": job_manager.count_queued_jobs(),
        "quality_tier_distribution": {
            "tier_1": 5,  # 5 jobs completed at tier 1
            "tier_2": 2,
            "tier_3": 0,
            "tier_4": 1,
            "tier_5": 0
        }
    }
```

### Progress Events

Include quality tier in SSE progress events:

```json
{
  "event_type": "job_started",
  "data": {
    "job_id": "abc123",
    "quality_tier": 1,
    "quality_score": 100,
    "estimated_time_seconds": 120
  }
}
```

---

## Rollout Plan

### Phase 1: Core Resource Tracking (High Priority)
- Implement `GPUResourceTracker` class
- Add to `main.py` initialization
- Add basic unit tests
- **Goal:** Prevent concurrent job OOM

### Phase 2: JobManager Integration (High Priority)
- Add semaphore enforcement to `JobManager`
- Integrate `GPUResourceTracker` into job start/stop
- Add basic resource reservation
- **Goal:** Hard enforcement of max_concurrent_jobs

### Phase 3: System Capability Detection (Medium Priority)
- Determine maximum quality tier system can support at startup
- Store as system-wide default tier
- Add VRAM estimation to model configs
- **Goal:** All jobs run at maximum quality system can support (never degrade for concurrency)

### Phase 4: Testing and Validation (Medium Priority)
- Write comprehensive unit tests
- Write integration tests for concurrent scenarios
- Test with mock low-memory systems
- **Goal:** Verify no regressions, proper behavior

### Phase 5: Monitoring and Observability (Low Priority)
- Add structured logging
- Create resource status endpoint
- Add quality metrics to progress events
- **Goal:** Production visibility

### Phase 6: Batch Processing Enhancements (Future)
- Optional parallel document processing within batches
- Shared model instance pool (if beneficial)
- **Goal:** Improved batch throughput

---

## Success Criteria

### Must Have (Phase 1-2)
- ✅ No system crashes due to resource exhaustion
- ✅ `max_concurrent_jobs` is enforced
- ✅ Jobs queue when resources unavailable
- ✅ Resources properly released on job completion/failure

### Should Have (Phase 3-4)
- ✅ System capability detection at startup
- ✅ All jobs run at system's maximum quality tier
- ✅ Jobs queue serially when resources in use (NEVER degrade for concurrency)
- ✅ Lower tiers only used when system hardware cannot support Tier 1
- ✅ Comprehensive test coverage (>80%)

### Nice to Have (Phase 5-6)
- ✅ Real-time resource monitoring endpoint
- ✅ Quality tier metrics and logging
- ✅ Model instance sharing across jobs
- ⚠️ Parallel batch processing: ONLY if both jobs can run at maximum quality tier simultaneously

---

## Open Questions

1. **Job timeout values?**
   - How long should a job wait in queue before failing?
   - Recommendation: 5 minutes default, configurable per request

2. **User-selectable quality tiers?**
   - Should users be able to request specific tiers via API?
   - Recommendation: Add optional `quality_preference` parameter

3. **Dynamic tier adjustment?**
   - Should running jobs be downgraded if higher-priority jobs arrive?
   - Recommendation: No - too complex, keep it simple

4. **Model preloading?**
   - Should we preload models at startup to reduce first-job latency?
   - Recommendation: Optional via config, disabled by default

---

## References

### External Documentation
- [HuggingFace Transformers - Model Loading](https://huggingface.co/docs/transformers/main_classes/model#large-model-loading)
- [HuggingFace Accelerate - Device Map](https://huggingface.co/docs/accelerate/usage_guides/big_modeling)
- [PyTorch CUDA Memory Management](https://pytorch.org/docs/stable/notes/cuda.html#memory-management)
- [bitsandbytes Quantization](https://github.com/TimDettmers/bitsandbytes)

### Related Specifications
- `inline-progress-batch-processing-spec.md` - Batch processing and SSE progress streaming
- `model_configs.yaml` - Model configuration and parameters
- `quality_tiers.yaml` - Quality tier definitions (to be created)

---

## Appendix A: VRAM Estimation Methodology

### DeepSeek-OCR Memory Breakdown

```
Base Model Weights: 6.0 GB
  - Loaded once per job
  - Shared across all pages
  - Reduced by quantization (int8: 3GB, int4: 1.5GB)

Inference Overhead (300 DPI, with crops):
  - Image preprocessing: 0.5 GB
  - Crop generation (8 crops): 2.0 GB
  - Model activations per crop: 0.5 GB
  - Batch processing overhead: 4.5 GB
  Total: 7.5 GB

Inference Overhead (300 DPI, no crops):
  - Image preprocessing: 0.5 GB
  - Model activations (single pass): 1.0 GB
  - Batch processing overhead: 2.0 GB
  Total: 3.5 GB

Total Peak (with crops): 6.0 + 7.5 = 13.5 GB
Total Peak (no crops): 6.0 + 3.5 = 9.5 GB
```

### Qwen2-VL Memory Breakdown

```
Base Model Weights:
  - 7B model: 14.0 GB
  - 2B model: 3.0 GB

Inference Overhead (300 DPI):
  - Image preprocessing: 0.5 GB
  - Model activations: 1.5 GB
  - Context handling: 1.75 GB
  Total: 3.75 GB

Total Peak (7B): 14.0 + 3.75 = 17.75 GB
Total Peak (2B): 3.0 + 3.75 = 6.75 GB
```

### Safety Margins

All estimates include 10% safety margin. Additionally:
- Reserve 2GB per GPU for CUDA overhead
- Reserve 4GB system RAM for OS operations
- Account for peak usage, not average

---

## Appendix B: Example API Responses

### Job Submission with Quality Tier Info

```json
POST /api/v1/jobs
Response 200:
{
  "job_id": "job_abc123",
  "status": "queued",
  "quality_tier": 1,
  "quality_score": 100,
  "estimated_vram_gb": 32,
  "estimated_duration_seconds": 120,
  "message": "Job queued for processing"
}
```

### Resource Status Endpoint

```json
GET /api/v1/monitoring/resources
Response 200:
{
  "gpus": {
    "0": {
      "total_gb": 22.0,
      "used_gb": 14.0,
      "available_gb": 8.0,
      "active_jobs": ["job_abc123"]
    },
    "1": {
      "total_gb": 22.0,
      "used_gb": 0,
      "available_gb": 22.0,
      "active_jobs": []
    }
  },
  "jobs": {
    "active": 1,
    "queued": 0,
    "max_concurrent": 2
  },
  "quality_stats_last_hour": {
    "tier_1": 45,
    "tier_2": 12,
    "tier_3": 3,
    "tier_4": 0,
    "tier_5": 0
  }
}
```

---

**End of Specification**
