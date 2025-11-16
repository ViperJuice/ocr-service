# BAML Integration - Phase 2.2 Implementation Plan (Revised)

**Date**: 2025-11-15
**Status**: 📋 **READY FOR IMPLEMENTATION**
**Estimated Time**: 30 minutes
**Complexity**: Low (uses existing infrastructure)

---

## Summary

Phase 2.2 adds enhanced metadata to existing merge page streaming events. The infrastructure already exists from Phase 2.1 - we just need to enrich the `emit_merge_page()` call with processing time and total pages metadata.

**Key Insight**: The user's original plan proposed 8+ files and 4-6 hours of work, but analysis shows the functionality already exists. We only need to add 2 parameters to an existing method.

---

## What Changed from Original Plan

### Original Plan Issues Identified

1. **Wrong Emitter Target**: Original plan targeted `ProgressEmitter`, but merge events use `ResultEmitter`
2. **Threading Anti-Pattern**: Proposed creating new event loops per emission
3. **Unnecessary Parameters**: Proposed adding parameters that already exist from Phase 2.1
4. **Overcomplicated**: 8+ files, new methods, custom threading logic

### Revised Approach

1. **Use Existing Infrastructure**: `ResultEmitter.emit_merge_page()` already called at [staged_pipeline.py:620](src/preprocessing/staged_pipeline.py#L620)
2. **Minimal Changes**: Add 2 parameters to existing method signature
3. **Existing Patterns**: Use `run_async_in_thread()` with existing `self._event_loop`
4. **Simple Update**: 2 backend files + 1 frontend file = ~10 lines of code

---

## Files to Modify

### 1. Backend: [src/api/services/result_emitter.py](src/api/services/result_emitter.py)

**Current Implementation** (existing code):
```python
def emit_merge_page(self, job_id: str, page_num: int, merged_text: str):
    """Emit merged page result"""
    event_data = {
        "job_id": job_id,
        "page_num": page_num,
        "merged_text": merged_text,
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }
    self._emit_event("merge_page", event_data)
```

**Revised Implementation** (add 2 parameters):
```python
def emit_merge_page(
    self,
    job_id: str,
    page_num: int,
    merged_text: str,
    processing_time: Optional[float] = None,  # NEW: Time in seconds
    total_pages: Optional[int] = None         # NEW: Total pages in job
):
    """Emit merged page result with enhanced metadata"""
    event_data = {
        "job_id": job_id,
        "page_num": page_num,
        "merged_text": merged_text,
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }

    # Add optional metadata
    if processing_time is not None:
        event_data["processing_time"] = processing_time
    if total_pages is not None:
        event_data["total_pages"] = total_pages

    self._emit_event("merge_page", event_data)
```

**Changes**:
- ✅ Add 2 optional parameters: `processing_time`, `total_pages`
- ✅ Include them in `event_data` if provided
- ✅ Backward compatible (parameters are optional)

**Lines Modified**: ~8 lines added to existing method

---

### 2. Backend: [src/preprocessing/staged_pipeline.py](src/preprocessing/staged_pipeline.py)

**Current Call Site** (line 620, existing code):
```python
# Emit merged result to SSE clients
if self.result_emitter and self.job_id:
    self.result_emitter.emit_merge_page(self.job_id, page_num, merged_text)
```

**Revised Call** (add metadata parameters):
```python
# Emit merged result to SSE clients with metadata
if self.result_emitter and self.job_id:
    self.result_emitter.emit_merge_page(
        job_id=self.job_id,
        page_num=page_num,
        merged_text=merged_text,
        processing_time=merge_model_result.processing_time,  # From OCRResult
        total_pages=self.total_pages                         # Already tracked
    )
```

**Changes**:
- ✅ Pass `processing_time` from `merge_model_result.processing_time` (OCRResult object)
- ✅ Pass `total_pages` from `self.total_pages` (already tracked in processor)
- ✅ No new parameters needed in __init__ (all already exist from Phase 2.1)

**Lines Modified**: 1 call site update (~5 lines)

**Note**: Uses existing `run_async_in_thread()` pattern already in place for other emissions. No threading changes needed.

---

### 3. Frontend: [web/lib/types.ts](web/lib/types.ts)

**Current Type** (existing):
```typescript
export interface MergePageEvent {
  job_id: string;
  page_num: number;
  merged_text: string;
  timestamp: string;
}
```

**Enhanced Type** (add optional metadata):
```typescript
export interface MergePageEvent {
  job_id: string;
  page_num: number;
  merged_text: string;
  timestamp: string;
  processing_time?: number;  // NEW: Processing time in seconds
  total_pages?: number;      // NEW: Total pages in job
}
```

**Changes**:
- ✅ Add 2 optional fields matching backend event data
- ✅ Backward compatible (fields are optional)

**Lines Modified**: 2 lines added to existing interface

---

## Implementation Checklist

### Backend Changes (10 minutes)

- [ ] **File**: [src/api/services/result_emitter.py](src/api/services/result_emitter.py)
  - [ ] Add `processing_time: Optional[float] = None` parameter to `emit_merge_page()`
  - [ ] Add `total_pages: Optional[int] = None` parameter to `emit_merge_page()`
  - [ ] Include metadata in `event_data` dict if provided
  - [ ] Verify backward compatibility (parameters are optional)

- [ ] **File**: [src/preprocessing/staged_pipeline.py](src/preprocessing/staged_pipeline.py)
  - [ ] Update `emit_merge_page()` call at line 620
  - [ ] Pass `processing_time=merge_model_result.processing_time`
  - [ ] Pass `total_pages=self.total_pages`
  - [ ] Verify `merge_model_result` is OCRResult with `processing_time` field
  - [ ] Verify `self.total_pages` is already tracked

### Frontend Changes (10 minutes)

- [ ] **File**: [web/lib/types.ts](web/lib/types.ts)
  - [ ] Add `processing_time?: number` to `MergePageEvent` interface
  - [ ] Add `total_pages?: number` to `MergePageEvent` interface
  - [ ] Verify TypeScript compilation succeeds

### Testing (10 minutes)

- [ ] **Integration Test**: Process a multi-page PDF
  - [ ] Verify SSE events include `processing_time`
  - [ ] Verify SSE events include `total_pages`
  - [ ] Verify existing functionality still works
  - [ ] Check browser console for TypeScript errors

- [ ] **Backward Compatibility Test**: Process job without metadata
  - [ ] Verify events still emit without optional fields
  - [ ] Verify frontend handles missing fields gracefully

---

## Testing Instructions

### Backend Test (Command Line)

```bash
# Start containers (if not running)
docker compose up -d

# Start API server
uv run uvicorn src.api.main:app --reload

# In another terminal, monitor SSE events
curl -N http://localhost:8000/results/stream
```

### Integration Test (Python)

```python
# Test file: test_phase2_2_streaming.py
import asyncio
from pathlib import Path

async def test_merge_streaming_metadata():
    """Verify merge page events include metadata"""

    # Process a PDF
    response = requests.post(
        "http://localhost:8000/jobs",
        json={
            "file_path": "test.pdf",
            "page_ranges": "1-3"
        }
    )
    job_id = response.json()["job_id"]

    # Listen to SSE stream
    with requests.get(f"http://localhost:8000/results/stream", stream=True) as r:
        for line in r.iter_lines():
            if line.startswith(b"data:"):
                event = json.loads(line[5:])

                if event.get("event") == "merge_page":
                    print(f"✓ Merge page {event['page_num']}")
                    print(f"  Processing time: {event.get('processing_time', 'N/A')}s")
                    print(f"  Total pages: {event.get('total_pages', 'N/A')}")

                    # Assertions
                    assert "processing_time" in event
                    assert "total_pages" in event
                    assert event["processing_time"] > 0
                    assert event["total_pages"] >= event["page_num"]

asyncio.run(test_merge_streaming_metadata())
```

### Frontend Test (Browser Console)

```javascript
// Open http://localhost:3000 and run in console
const eventSource = new EventSource('http://localhost:8000/results/stream');

eventSource.addEventListener('merge_page', (e) => {
  const data = JSON.parse(e.data);
  console.log('Merge Page Event:', {
    page: data.page_num,
    processingTime: data.processing_time,  // Should be present
    totalPages: data.total_pages,          // Should be present
    textLength: data.merged_text.length
  });
});
```

---

## Benefits of Revised Approach

| Aspect | Original Plan | Revised Plan |
|--------|--------------|--------------|
| **Files Modified** | 8+ files | 2 backend + 1 frontend = 3 files |
| **New Methods** | `emit_merge_chunk()`, new threading logic | 0 new methods (use existing) |
| **Threading Changes** | Custom event loop management | 0 (use existing pattern) |
| **Parameters Added** | 3-4 new __init__ parameters | 0 (use existing) |
| **Lines of Code** | 100+ lines | ~10 lines |
| **Estimated Time** | 4-6 hours | 30 minutes |
| **Complexity** | High (new infrastructure) | Low (parameter addition) |
| **Risk** | Medium (threading issues) | Very low (backward compatible) |

---

## Why This Works

### 1. Infrastructure Already Exists (Phase 2.1)

From [src/preprocessing/staged_pipeline.py:83-113](src/preprocessing/staged_pipeline.py#L83-L113):
```python
def __init__(
    self,
    model_manager,
    pdf_handler: PDFHandler,
    baml_ocr_service: Optional[Any] = None,
    result_emitter: Optional[Any] = None,  # ✅ Already exists
    job_id: Optional[str] = None,          # ✅ Already exists
    event_loop=None                        # ✅ Already exists
):
    self.result_emitter = result_emitter
    self.job_id = job_id
    self._event_loop = event_loop
```

### 2. Merge Events Already Emitted (Phase 2.1)

From [src/preprocessing/staged_pipeline.py:620](src/preprocessing/staged_pipeline.py#L620):
```python
# Emit merged result to SSE clients
if self.result_emitter and self.job_id:
    self.result_emitter.emit_merge_page(self.job_id, page_num, merged_text)
```

### 3. Metadata Already Available

- **`processing_time`**: Comes from `OCRResult.processing_time` (BAML integration from Phase 2.1)
- **`total_pages`**: Already tracked in `self.total_pages` (existing pipeline state)

### 4. Thread-Safe Async Already Handled

The `ResultEmitter._emit_event()` method already uses thread-safe async patterns internally. No changes needed.

---

## Success Criteria

After implementation, verify:

1. ✅ **SSE Events Include Metadata**: `processing_time` and `total_pages` present in merge page events
2. ✅ **Backward Compatible**: Existing code works without errors
3. ✅ **Frontend Types Match**: TypeScript interface matches backend event structure
4. ✅ **No Performance Impact**: Same performance as before (just 2 extra fields)
5. ✅ **No Threading Issues**: Events still emit correctly in async context

---

## Comparison to Original Plan

### Original Plan Proposed

**New Method in ProgressEmitter**:
```python
def emit_merge_chunk(self, job_id: str, page_num: int, chunk_text: str, chunk_index: int, total_chunks: int, parent_batch_id: str = None):
    # ... 30+ lines of new code ...
```

**New Threading Logic**:
```python
def _run_async(self, coro):
    loop = asyncio.new_event_loop()  # ❌ Anti-pattern
    thread = threading.Thread(target=..., daemon=True)  # ❌ New thread per page
```

**New __init__ Parameters**:
```python
def __init__(
    # ... existing ...
    progress_emitter: Optional[ProgressEmitter] = None,  # ❌ Not needed
    job_id: Optional[str] = None,  # ✅ Already exists
    parent_batch_id: Optional[str] = None  # ❌ Not needed for Phase 2.2
):
```

### Revised Plan Uses

**Existing Method with 2 Parameters**:
```python
def emit_merge_page(
    self,
    job_id: str,
    page_num: int,
    merged_text: str,
    processing_time: Optional[float] = None,  # ✅ Just add this
    total_pages: Optional[int] = None         # ✅ And this
):
```

**Existing Threading Pattern**:
```python
# Already handled by ResultEmitter._emit_event() internally
# Uses existing event loop from Phase 2.1
```

**Existing Parameters**:
```python
# All required parameters already exist from Phase 2.1:
# - self.result_emitter
# - self.job_id
# - self._event_loop
```

---

## Migration Path

Phase 2.2 is **purely additive** and **100% backward compatible**:

1. ✅ New parameters are **optional** (`Optional[float]`, `Optional[int]`)
2. ✅ Existing calls work without changes (defaults to `None`)
3. ✅ Frontend types use **optional fields** (`processing_time?`, `total_pages?`)
4. ✅ No breaking changes to API contracts
5. ✅ Can deploy backend and frontend independently

**Deployment Order** (any order works):
```
Option A: Backend → Frontend
Option B: Frontend → Backend
Option C: Deploy together
```

All three options work because changes are backward compatible.

---

## Phase 2.3 Compatibility

This Phase 2.2 implementation prepares for Phase 2.3 (Frontend Type Sync):

**Current Type Definition** (manual):
```typescript
// web/lib/types.ts
export interface MergePageEvent {
  processing_time?: number;
  total_pages?: number;
}
```

**Future BAML-Generated Type** (Phase 2.3):
```typescript
// Import from BAML client (if we choose Option B or C)
import { MergePageEvent } from '@/baml_client/types';
```

Phase 2.2 changes are compatible with any Phase 2.3 approach chosen.

---

## Estimated Timeline

| Task | Time | Who |
|------|------|-----|
| **Backend: result_emitter.py** | 5 min | Developer |
| **Backend: staged_pipeline.py** | 5 min | Developer |
| **Frontend: types.ts** | 5 min | Developer |
| **Integration Testing** | 10 min | Developer |
| **Code Review** | 5 min | Reviewer |
| **Total** | **30 min** | Team |

---

## Rollback Plan

If issues arise, rollback is trivial:

**Rollback Changes**:
1. Remove 2 parameters from `emit_merge_page()` signature
2. Revert call site to original 3-parameter call
3. Remove 2 fields from `MergePageEvent` TypeScript interface

**Rollback Time**: < 5 minutes

**Risk**: Very low (backward compatible changes)

---

## Next Steps After Phase 2.2

Once Phase 2.2 is complete and tested:

1. **Phase 2.3 Decision**: Choose frontend type sync approach (Option A/B/C)
2. **Phase 3**: Remove fallback mechanism once BAML proven stable
3. **Phase 4**: Generate Python client code directly from BAML (future)

---

## Conclusion

Phase 2.2 is a **10-line enhancement** to existing infrastructure, not a new feature requiring 4-6 hours of development. The revised plan:

✅ Uses existing `ResultEmitter.emit_merge_page()` method
✅ Adds only 2 optional parameters
✅ Requires 0 new threading logic
✅ Requires 0 new __init__ parameters
✅ Takes 30 minutes instead of 4-6 hours
✅ Is 100% backward compatible
✅ Has minimal risk

**Ready for implementation immediately.**

---

**Generated**: 2025-11-15
**Complexity**: Low
**Risk**: Very Low
**Estimated Time**: 30 minutes
**Status**: 📋 Ready for Implementation
