# Phase 3 Implementation Plan: Real-Time Infrastructure

**Spec Reference:** [MASTER_ROADMAP.md](./MASTER_ROADMAP.md#phase-3-real-time-infrastructure--partially-complete)
**Phase Name:** Phase 3 - Real-Time Infrastructure
**Status:** In Progress (90% complete, SystemMonitor bug blocking testing)
**Created:** 2025-11-15
**Last Updated:** 2025-11-15

---

## Table of Contents

1. [Phase Scope & Objectives](#phase-scope--objectives)
2. [Architectural Baseline](#architectural-baseline)
3. [Code-Level Interface Contracts](#code-level-interface-contracts)
4. [Exhaustive Change List](#exhaustive-change-list)
5. [Swim Lane Assignments](#swim-lane-assignments)
6. [Dependencies & Sequencing](#dependencies--sequencing)
7. [Testing Strategy](#testing-strategy)
8. [Success Criteria](#success-criteria)

---

## Phase Scope & Objectives

### Primary Goals

1. **Fix SystemMonitor Bug** - Resolve null safety crash preventing frontend load
2. **Validate Realtime Subscriptions** - Test WebSocket updates vs SSE
3. **Performance Comparison** - Document latency differences (SSE vs Realtime)
4. **Complete Phase 3** - Finalize dual-subscription infrastructure

### What's Already Complete (90%)

- ✅ Supabase client setup ([web/lib/supabase.ts](../web/lib/supabase.ts))
- ✅ Database type definitions ([web/types/database.ts](../web/types/database.ts))
- ✅ Realtime job subscription hook ([web/hooks/useRealtimeJob.ts](../web/hooks/useRealtimeJob.ts))
- ✅ Realtime batch subscription hook ([web/hooks/useRealtimeBatch.ts](../web/hooks/useRealtimeBatch.ts))
- ✅ Dual-subscription integration in useOcrJob and useBatchJob
- ✅ BAML TypeScript generator fix (ESM → CJS)
- ✅ Frontend type sync from BAML
- ✅ Frontend builds successfully (when SystemMonitor is not rendered)

### What's Pending (10%)

- 🐛 **SystemMonitor null safety** - Crashes at line 93 when `current.gpus` is undefined
- ⏳ Integration testing ([test_realtime_simple.sh](../test_realtime_simple.sh))
- ⏳ Performance validation (latency comparison)
- ⏳ Documentation of results

### Out of Scope (Deferred to Phase 4)

- Removing SSE infrastructure
- Removing in-memory state
- Making Realtime the exclusive update mechanism

---

## Architectural Baseline

### A. Component Catalog (Post-Implementation)

#### Modified Files

| File Path | Status | Purpose |
|-----------|--------|---------|
| [web/components/SystemMonitor.tsx](../web/components/SystemMonitor.tsx) | **MODIFY** | Fix null safety for GPU data |
| [web/hooks/useSystemMetrics.ts](../web/hooks/useSystemMetrics.ts) | **VERIFY** | Ensure proper null handling |
| [test_realtime_simple.sh](../test_realtime_simple.sh) | **EXECUTE** | Run integration tests |
| [specs/PHASE_3_TEST_RESULTS.md](./PHASE_3_TEST_RESULTS.md) | **CREATE** | Document test results and latency |

#### Existing Files (No Changes Needed)

These files are already complete and functional:

- [web/lib/supabase.ts](../web/lib/supabase.ts) - Supabase client with Realtime config
- [web/types/database.ts](../web/types/database.ts) - Generated database types
- [web/hooks/useRealtimeJob.ts](../web/hooks/useRealtimeJob.ts) - Job subscription hook
- [web/hooks/useRealtimeBatch.ts](../web/hooks/useRealtimeBatch.ts) - Batch subscription hook
- [web/hooks/useOcrJob.ts](../web/hooks/useOcrJob.ts) - Dual-subscription integration
- [web/hooks/useBatchJob.ts](../web/hooks/useBatchJob.ts) - Dual-subscription integration

### B. Classes / Types (Modified)

#### SystemMonitor Component

**File:** `web/components/SystemMonitor.tsx`

**Current Issue:** Line 93 crashes when `current.gpus` is undefined

```typescript
// CURRENT (BROKEN):
{current.gpus.map((gpu) => (  // ❌ crashes if gpus is undefined
  <div key={gpu.id}>...</div>
))}

// REQUIRED FIX:
{current.gpus && current.gpus.length > 0 ? (  // ✅ null-safe
  current.gpus.map((gpu) => <div key={gpu.id}>...</div>)
) : (
  <div className="text-gray-400 text-sm">No GPU data available</div>
)}
```

**Type Definition (from lib/types.ts):**

```typescript
export interface SystemMetrics {
  timestamp: number;
  cpu_percent: number | null;
  ram_percent: number | null;
  ram_used_mb: number | null;
  ram_total_mb: number | null;
  gpus?: GpuMetrics[];  // ⚠️ Optional - can be undefined
}

export interface GpuMetrics {
  id: number;
  name: string | null;
  memory_used_mb: number;
  memory_total_mb: number;
  memory_percent: number;
  utilization_percent: number;
  temperature_c: number | null;
}
```

**Required Changes:**

1. Add null checks before mapping over `current.gpus`
2. Add fallback UI when GPU data is unavailable
3. Add null safety for individual GPU fields (`gpu.name`, `gpu.temperature_c`)

### C. Functions / Methods (Modified)

#### SystemMonitor.tsx

**Function:** `SystemMonitor` component (lines 16-250+)

**Modification Type:** Bug fix (null safety)

**Changes:**
- Add conditional rendering for `current.gpus`
- Add fallback UI for missing GPU data
- Ensure all GPU field access is null-safe

**No signature changes** - Props interface remains identical:

```typescript
interface SystemMonitorProps {
  current: SystemMetrics | null;
  history: SystemMetrics[];
  alerts: Alert[];
  isConnected: boolean;
}
```

### D. Data Structures (No Changes)

All data structures already defined and operational:

- `SystemMetrics` (lib/types.ts) - Already has optional `gpus?` field
- `GpuMetrics` (lib/types.ts) - Already has nullable fields
- Supabase database types (web/types/database.ts) - Generated, no changes needed
- Realtime subscription types - Already complete in hooks

---

## Code-Level Interface Contracts

### Interface Freeze Gate: IF-0-Phase3

**Status:** ✅ FROZEN (No interface changes in Phase 3)

All interfaces were defined in Phases 1-2 and remain unchanged:

#### 1. Supabase Realtime WebSocket Interface

**Provider:** Supabase Realtime Server
**Consumer:** Frontend hooks (useRealtimeJob, useRealtimeBatch)

**Contract:**
```typescript
// Channel subscription
supabase
  .channel(`job:${jobId}`)
  .on(
    'postgres_changes',
    {
      event: '*',           // INSERT, UPDATE, DELETE
      schema: 'public',
      table: 'jobs',
      filter: `job_id=eq.${jobId}`
    },
    (payload) => {
      const newJob = payload.new as Job  // Type: Database['public']['Tables']['jobs']['Row']
    }
  )
  .subscribe((status) => {
    // status: 'SUBSCRIBED' | 'CHANNEL_ERROR' | 'TIMED_OUT' | ...
  })
```

**Error Behavior:**
- Network failure: Automatic reconnection (Supabase SDK handles)
- Channel error: Error state set in hook, reported to consumer
- Timeout: Error state set in hook, reported to consumer

**Invariants:**
- Subscription receives ALL changes to filtered rows
- Updates delivered in chronological order
- Automatic cleanup on channel removal

#### 2. SystemMonitor Component Interface

**Provider:** SystemMonitor component
**Consumer:** Parent components (Dashboard, etc.)

**Contract (Unchanged):**
```typescript
interface SystemMonitorProps {
  current: SystemMetrics | null;    // Null when loading
  history: SystemMetrics[];          // Historical data points
  alerts: Alert[];                   // Active system alerts
  isConnected: boolean;              // SSE connection status
}

// SystemMetrics type (defined in lib/types.ts)
export interface SystemMetrics {
  timestamp: number;
  cpu_percent: number | null;
  ram_percent: number | null;
  ram_used_mb: number | null;
  ram_total_mb: number | null;
  gpus?: GpuMetrics[];  // ⚠️ Optional - Phase 3 fix handles this
}
```

**Error Behavior:**
- `current === null` → Show "Loading metrics..." spinner
- `current.gpus === undefined` → Show "No GPU data available" (Phase 3 fix)
- `current.gpus === []` → Show "No GPUs detected"

**Rendering Invariants:**
- Component MUST NOT crash when `current.gpus` is undefined
- Component MUST gracefully handle missing GPU fields
- Component MUST show loading state when `current === null`

#### 3. Test Interface (test_realtime_simple.sh)

**Provider:** Test script
**Consumer:** Human tester / CI system

**Contract:**
```bash
#!/bin/bash
# Prerequisites: All services running (Supabase, Docker, API, Frontend)
# Input: None
# Output: Console logs showing dual-subscription comparison
# Success: Exit code 0, latency metrics printed
# Failure: Exit code 1, error messages printed
```

**Test Flow:**
1. Check all services are running
2. Upload test PDF via API
3. Submit OCR job
4. Monitor console logs for dual-subscription output
5. Compare SSE vs Realtime latencies
6. Document results in PHASE_3_TEST_RESULTS.md

---

## Exhaustive Change List

### A. Add (New Files)

| File | Type | Purpose | Owner |
|------|------|---------|-------|
| `specs/PHASE_3_TEST_RESULTS.md` | Documentation | Test results and latency comparison | Testing Lane |

### B. Modify (Existing Files)

| File | Lines | Change Type | Owner | Description |
|------|-------|-------------|-------|-------------|
| `web/components/SystemMonitor.tsx` | 93-160 | Bug fix | Frontend Lane | Add null safety for `current.gpus` |
| `web/components/SystemMonitor.tsx` | 93 | Add conditional | Frontend Lane | Check if `gpus` exists before mapping |
| `web/components/SystemMonitor.tsx` | ~95 | Add fallback UI | Frontend Lane | Show message when no GPU data |

### C. Delete (None)

No files or code removed in Phase 3.

### D. Comment/Deprecate (None)

No deprecations in Phase 3 (deferred to Phase 4).

---

## Swim Lane Assignments

Phase 3 work is organized into 3 swim lanes that can run in parallel after the bug fix.

### Lane 1: Frontend Bug Fix (Critical Path)

**Owner:** Frontend Engineer
**Duration:** 30 minutes
**Prerequisites:** None
**Blocks:** Lane 2 (Testing) and Lane 3 (Documentation)

**Tasks:**

1. **Fix SystemMonitor.tsx null safety** (20 min)
   - File: [web/components/SystemMonitor.tsx](../web/components/SystemMonitor.tsx)
   - Lines: 93-160
   - Changes:
     - Add null check before `current.gpus.map()`
     - Add fallback UI for missing GPU data
     - Verify all GPU field accesses are null-safe
   - Test: Load frontend, ensure no crash

2. **Verify useSystemMetrics null handling** (10 min)
   - File: [web/hooks/useSystemMetrics.ts](../web/hooks/useSystemMetrics.ts)
   - Check: Ensure hook doesn't crash on missing GPU data
   - No changes expected (verification only)

**Deliverables:**
- ✅ Frontend loads without crashing
- ✅ SystemMonitor shows graceful fallback when GPU data missing
- ✅ Ready for integration testing

---

### Lane 2: Integration Testing (Blocked by Lane 1)

**Owner:** QA Engineer / Tester
**Duration:** 2 hours
**Prerequisites:** Lane 1 complete (frontend loads)
**Blocks:** None (parallel with Lane 3)

**Tasks:**

1. **Start all services** (10 min)
   ```bash
   # Terminal 1: Supabase
   supabase start

   # Terminal 2: GPU containers
   docker-compose up

   # Terminal 3: Backend API
   uv run uvicorn src.api.main:app --reload

   # Terminal 4: Frontend
   cd web && npm run dev
   ```

2. **Run integration test script** (30 min)
   ```bash
   bash test_realtime_simple.sh
   ```
   - Upload test PDF
   - Submit OCR job
   - Monitor dual-subscription logs
   - Capture console output

3. **Manual testing** (1 hour)
   - Open browser to http://localhost:3000
   - Upload PDF and submit job
   - Monitor browser console for:
     - `[PHASE 3.5] Realtime update received:` logs
     - `[SSE]` logs (from existing SSE implementation)
   - Compare latencies in console
   - Test multiple jobs concurrently
   - Test job cancellation
   - Test batch job monitoring

4. **Performance validation** (30 min)
   - Extract latency numbers from logs
   - Calculate averages: SSE vs Realtime
   - Document findings
   - Take screenshots of console logs

**Deliverables:**
- ✅ test_realtime_simple.sh passes
- ✅ Realtime subscriptions receive all updates
- ✅ Latency comparison data collected
- ✅ Screenshots captured

---

### Lane 3: Documentation (Blocked by Lane 1, Parallel with Lane 2)

**Owner:** Technical Writer / Engineer
**Duration:** 1 hour
**Prerequisites:** Lane 1 complete, Lane 2 in progress
**Blocks:** None

**Tasks:**

1. **Create test results document** (30 min)
   - File: `specs/PHASE_3_TEST_RESULTS.md`
   - Sections:
     - Test environment setup
     - Test cases executed
     - Latency comparison table (SSE vs Realtime)
     - Screenshots of console logs
     - Observed issues (if any)
     - Recommendations for Phase 4

2. **Update MASTER_ROADMAP.md** (15 min)
   - File: `specs/MASTER_ROADMAP.md`
   - Update Phase 3 status from "🔄 PARTIALLY COMPLETE" to "✅ COMPLETE"
   - Update "Current Status Dashboard" table
   - Add completion date

3. **Update IMPLEMENTATION_STATUS.md** (15 min)
   - File: `specifications/IMPLEMENTATION_STATUS.md`
   - Remove SystemMonitor bug from "Current Blockers"
   - Mark Phase 3 as complete
   - Add "Next Steps" section pointing to Phase 4

**Deliverables:**
- ✅ PHASE_3_TEST_RESULTS.md created
- ✅ MASTER_ROADMAP.md updated
- ✅ IMPLEMENTATION_STATUS.md updated
- ✅ Phase 3 officially closed

---

## Dependencies & Sequencing

### Critical Path

```
Lane 1 (Bug Fix)
    ↓
Lane 2 (Testing) ←→ Lane 3 (Documentation)
    ↓                      ↓
  Phase 3 Complete ←───────┘
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|------------|--------|
| Lane 1: Fix SystemMonitor | None | Lane 2, Lane 3 |
| Lane 2: Integration Testing | Lane 1 complete | None |
| Lane 3: Documentation | Lane 1 complete, Lane 2 partial | None |

### Sequencing Rules

1. **Lane 1 MUST complete first** - Frontend must load before testing
2. **Lane 2 and Lane 3 can run in parallel** - Documentation can start while testing is in progress
3. **Lane 3 needs Lane 2 results** - Test results document needs data from Lane 2

### Interface Freeze

All interfaces are frozen (IF-0-Phase3). No breaking changes allowed:
- ✅ SystemMonitor props interface unchanged
- ✅ Realtime hooks interface unchanged
- ✅ Database types unchanged
- ✅ BAML types unchanged

---

## Testing Strategy

### Unit Tests (None Required)

No new logic added in Phase 3, only null safety fixes. Existing unit tests remain valid.

### Integration Tests

#### Test Script: test_realtime_simple.sh

**Purpose:** Validate Realtime subscriptions work end-to-end

**Prerequisites:**
- All services running (Supabase, Docker, API, Frontend)
- Frontend loads without crashing

**Steps:**
1. Upload test PDF via API
2. Submit OCR job
3. Monitor console logs for dual-subscription output
4. Verify Realtime updates received
5. Compare latency vs SSE

**Expected Output:**
```
[PHASE 3.5] Realtime subscription status: SUBSCRIBED
[PHASE 3.5] Realtime update received: {
  jobId: "job_123",
  status: "processing",
  progress_pct: 33,
  latency: "45ms"
}
[SSE] Page complete event received: {
  jobId: "job_123",
  pageNum: 1,
  latency: "120ms"
}
```

**Success Criteria:**
- ✅ Realtime subscription connects (status: SUBSCRIBED)
- ✅ Updates received for all job state changes
- ✅ Latency < SSE latency (Realtime should be faster)
- ✅ No errors in console

#### Manual Testing Checklist

- [ ] Upload PDF, submit job, see real-time progress
- [ ] Cancel job mid-processing, verify cancellation received via Realtime
- [ ] Submit batch job, monitor batch progress via Realtime
- [ ] Test concurrent jobs (2+ jobs running simultaneously)
- [ ] Test network interruption (disconnect/reconnect WiFi)
- [ ] Verify frontend reconnects automatically after network restored
- [ ] Check database via Supabase Studio to confirm job state matches UI

### Performance Testing

**Metrics to Collect:**

| Metric | SSE Baseline | Realtime Target | Measurement Method |
|--------|--------------|-----------------|-------------------|
| Update latency (avg) | ~100-200ms | <100ms | Console logs |
| Update latency (p95) | ~300ms | <150ms | Console logs |
| Connection overhead | N/A (HTTP) | <2s | Subscription status callback |
| Reconnection time | N/A | <5s | Manual disconnect test |

**Data Collection:**
- Browser console logs (both SSE and Realtime)
- Chrome DevTools Network tab (WebSocket frames)
- Screenshots of console output
- Copy logs to PHASE_3_TEST_RESULTS.md

---

## Success Criteria

### Phase 3 Complete When:

- [x] SystemMonitor bug fixed (null safety)
- [ ] Frontend loads without crashing
- [ ] Integration test script passes
- [ ] Realtime subscriptions working end-to-end
- [ ] Latency comparison documented
- [ ] Test results documented (PHASE_3_TEST_RESULTS.md)
- [ ] MASTER_ROADMAP.md updated to mark Phase 3 complete

### Performance Goals:

- [ ] Realtime latency < SSE latency (lower is better)
- [ ] Realtime connection established in <2s
- [ ] Zero crashes or errors during testing
- [ ] Dual-subscription logs clearly show both mechanisms working

### Documentation Complete:

- [ ] PHASE_3_TEST_RESULTS.md created with:
  - Test environment details
  - Latency comparison table
  - Console log screenshots
  - Recommendations for Phase 4
- [ ] MASTER_ROADMAP.md updated (Phase 3 → ✅ COMPLETE)
- [ ] IMPLEMENTATION_STATUS.md updated (blocker removed)

---

## Rollback Plan

If Phase 3 testing reveals critical issues:

### Rollback Trigger:

- Realtime subscriptions fail to receive updates
- Realtime latency worse than SSE
- Frontend crashes persist after SystemMonitor fix
- Database connection issues

### Rollback Steps:

1. **Revert SystemMonitor changes** (if needed)
   ```bash
   git checkout HEAD -- web/components/SystemMonitor.tsx
   ```

2. **Comment out Realtime hooks** (if needed)
   - Keep code in place, just disable usage
   - Fall back to SSE-only updates

3. **Document issues** in PHASE_3_TEST_RESULTS.md
   - What went wrong
   - Why Realtime didn't work
   - What needs to be fixed before retry

4. **Mark Phase 3 as "Partially Complete"** in MASTER_ROADMAP.md
   - Update status dashboard
   - Add blockers section

### No Breaking Changes:

- SSE infrastructure remains intact (Phase 4 will remove it)
- In-memory state remains intact (Phase 4 will remove it)
- Dual-subscription is additive only (can be disabled without breaking existing features)

---

## Next Steps After Phase 3

Once Phase 3 is complete and validated:

1. **Review Phase 4 specification** ([MASTER_ROADMAP.md#phase-4](./MASTER_ROADMAP.md#phase-4-infrastructure-migration--pending))
2. **Plan SSE removal** (comment out endpoints, stop emitting events)
3. **Plan in-memory state removal** (database as single source of truth)
4. **Create Phase 4 implementation plan** (use this document as template)

---

## Appendix: File Reference

### Files Modified in Phase 3

| File | Path | Purpose |
|------|------|---------|
| SystemMonitor.tsx | [web/components/SystemMonitor.tsx](../web/components/SystemMonitor.tsx) | GPU metrics display (bug fix) |

### Files Created in Phase 3

| File | Path | Purpose |
|------|------|---------|
| PHASE_3_TEST_RESULTS.md | [specs/PHASE_3_TEST_RESULTS.md](./PHASE_3_TEST_RESULTS.md) | Test results and latency data |

### Files Not Modified (Reference Only)

These files are complete from earlier Phase 3 work:

| File | Path | Status |
|------|------|--------|
| supabase.ts | [web/lib/supabase.ts](../web/lib/supabase.ts) | ✅ Complete |
| database.ts | [web/types/database.ts](../web/types/database.ts) | ✅ Complete |
| useRealtimeJob.ts | [web/hooks/useRealtimeJob.ts](../web/hooks/useRealtimeJob.ts) | ✅ Complete |
| useRealtimeBatch.ts | [web/hooks/useRealtimeBatch.ts](../web/hooks/useRealtimeBatch.ts) | ✅ Complete |
| useOcrJob.ts | [web/hooks/useOcrJob.ts](../web/hooks/useOcrJob.ts) | ✅ Complete (dual-subscription) |
| useBatchJob.ts | [web/hooks/useBatchJob.ts](../web/hooks/useBatchJob.ts) | ✅ Complete (dual-subscription) |

---

**END OF PHASE 3 IMPLEMENTATION PLAN**
