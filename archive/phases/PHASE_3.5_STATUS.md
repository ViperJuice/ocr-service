# Phase 3.5: Supabase Realtime Integration - Status Report

## Overview

Phase 3.5 implements dual-subscription monitoring using Supabase Realtime WebSocket subscriptions alongside existing SSE (Server-Sent Events) polling. This allows real-time comparison of data delivery latency and accuracy between HTTP polling and WebSocket push mechanisms.

## Implementation Status: ✅ COMPLETE

All frontend code for Phase 3.5 has been implemented and is ready for testing.

### Completed Components

#### 1. Supabase Client Setup
- **File**: `web/lib/supabase.ts`
- **Status**: ✅ Created
- **Purpose**: Initializes Supabase client with Realtime configuration
- **Configuration**: 10 events/second throttle

#### 2. Database Type Definitions
- **File**: `web/types/database.ts`
- **Status**: ✅ Created
- **Purpose**: Full TypeScript type safety for database schema
- **Coverage**: Jobs, batch_jobs, files, directories, and all related types

#### 3. Realtime Job Subscription Hook
- **File**: `web/hooks/useRealtimeJob.ts`
- **Status**: ✅ Created
- **Purpose**: WebSocket subscription to individual job updates
- **Features**:
  - Auto-connect/disconnect based on jobId
  - Connection status tracking
  - Latency measurement
  - Error handling
  - Automatic cleanup on unmount

#### 4. Realtime Batch Subscription Hook
- **File**: `web/hooks/useRealtimeBatch.ts`
- **Status**: ✅ Created
- **Purpose**: WebSocket subscription to batch job updates
- **Features**: Same as useRealtimeJob, adapted for batch_jobs table

#### 5. Dual-Subscription Integration
- **File**: `web/hooks/useOcrJob.ts` (Lines 130-167)
- **Status**: ✅ Modified
- **Changes**:
  - Added Realtime subscription to existing `useJobStatus` hook
  - Logs comparison data between SSE and Realtime
  - No user-facing changes (continues returning SSE data)
  - Console logging for validation

#### 6. Batch Job Status Hook
- **File**: `web/hooks/useBatchJob.ts` (Lines 77-116)
- **Status**: ✅ Created
- **Purpose**: New `useBatchJobStatus` export for batch monitoring
- **Features**: Same dual-subscription pattern as job monitoring

## Backend Fixes

### Fixed: AsyncIO UnboundLocalError
- **File**: `src/api/services/job_manager.py`
- **Issue**: `UnboundLocalError: cannot access local variable 'asyncio'`
- **Root Cause**: Duplicate `import asyncio` on line 355 created local variable shadowing
- **Fix**: Removed duplicate import statement
- **Status**: ✅ Fixed

## Testing Status: ⚠️ BLOCKED

### Blocker: SystemMonitor Component Crash

**Error**:
```
TypeError: Cannot read properties of undefined (reading 'map')
at SystemMonitor (components/SystemMonitor.tsx:93:23)
```

**Root Cause**: SystemMonitor assumes `current.gpus` always exists, but it's undefined when GPU monitoring is disabled.

**Impact**: Frontend at http://localhost:3000 crashes on load, preventing Phase 3.5 Realtime testing.

**Location**: `web/components/SystemMonitor.tsx:93`

**Affected Lines**:
- Line 43: `current.gpus.length` - assumes gpus exists
- Line 93: `current.gpus.map(...)` - tries to map undefined array
- Line 177+: Various properties assumed to exist (`ram_percent`, `queue`, `active_model`)

**Status**: ⏳ Fix planned, awaiting approval

## Testing Instructions (Once Blocker is Fixed)

### Prerequisites
- Next.js dev server running at http://localhost:3000
- Backend API server running at http://localhost:8000
- Supabase instance running at http://localhost:54321
- SystemMonitor.tsx fixed with null safety

### Manual Testing Procedure

1. **Start the test script**:
   ```bash
   bash test_realtime_simple.sh
   ```
   This creates test job: `8e8d6040-7497-42d1-97d4-d2fbb9d1cacb`

2. **Open browser**:
   - Navigate to http://localhost:3000
   - Open browser DevTools console (F12)

3. **Trigger updates**:
   - Return to terminal running `test_realtime_simple.sh`
   - Press ENTER when prompted
   - Script will send progress updates every 2 seconds

4. **Verify in console**:
   Look for logs matching this pattern:
   ```
   [PHASE 3.5] Dual-Subscription Comparison: {
     jobId: "8e8d6040-7497-42d1-97d4-d2fbb9d1cacb",
     sse: {
       status: "processing",
       progress_pct: 25,
       pages_completed: 1,
       source: "polling"
     },
     realtime: {
       status: "processing",
       progress_pct: 25,
       pages_completed: 1,
       latency: "45ms",
       connected: true,
       source: "websocket"
     },
     match: {
       status: true,
       progress: true,
       pages: true
     }
   }
   ```

### Expected Behavior

#### ✅ Success Criteria
- Realtime subscription connects (`connected: true`)
- Updates appear in console with `[PHASE 3.5]` prefix
- Latency is measured and displayed (typically 20-100ms)
- SSE and Realtime data match (`match: { status: true, progress: true, pages: true }`)
- Updates arrive faster via WebSocket than SSE polling (lower latency)

#### ❌ Failure Indicators
- No console logs appearing
- `connected: false` in logs
- Error messages in Realtime section
- Data mismatch between SSE and Realtime
- No latency measurement

### Batch Testing
Repeat the same procedure using batch job endpoints and verifying `useBatchJobStatus` hook output.

## API Endpoints Reference

### Job Endpoints
- **Upload**: `POST /api/v1/process/upload`
- **Submit Job**: `POST /api/v1/process/jobs`
- **Get Status**: `GET /api/v1/process/jobs/{job_id}`
- **Stream Results**: `GET /api/v1/process/jobs/{job_id}/stream-results` (SSE)

### Batch Endpoints
- **Upload Directory**: `POST /api/v1/process/upload-directory`
- **Submit Batch**: `POST /api/v1/process/batch`
- **Get Status**: `GET /api/v1/process/batch/{batch_job_id}`

## Known Issues (Unrelated to Phase 3.5)

1. **Database Write Timeouts**: Backend can't write jobs to database within 5-second timeout
2. **Missing numpy Module**: Backend OCR processing needs numpy installed
3. **Foreign Key Constraints**: Jobs fail to insert due to missing file references

**Workaround**: Test script bypasses backend by directly inserting into Supabase via REST API

## Environment Configuration

Required environment variables in `web/.env.local`:
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=http://localhost:54321
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

## Dependencies

### New Dependencies Added
```json
{
  "@supabase/supabase-js": "^2.39.0"
}
```

Installed via:
```bash
cd web && npm install @supabase/supabase-js
```

## Technical Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (Next.js)                                         │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ useJobStatus Hook                                    │  │
│  │                                                      │  │
│  │  ┌────────────────┐      ┌──────────────────┐      │  │
│  │  │ SSE Polling    │      │ Realtime WebSocket│      │  │
│  │  │ (React Query)  │      │ (useRealtimeJob)  │      │  │
│  │  │                │      │                   │      │  │
│  │  │ - 2s interval  │      │ - Instant push    │      │  │
│  │  │ - HTTP GET     │      │ - postgres_changes│      │  │
│  │  └────────┬───────┘      └────────┬──────────┘      │  │
│  │           │                       │                 │  │
│  │           └───────────┬───────────┘                 │  │
│  │                       │                             │  │
│  │                  Comparison                         │  │
│  │                  Console Log                        │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          │              │
                   HTTP   │              │ WebSocket
                          │              │
┌─────────────────────────┴──────────────┴───────────────────┐
│  Backend                                                    │
│                                                             │
│  ┌──────────────┐              ┌──────────────────┐        │
│  │ FastAPI      │              │ Supabase         │        │
│  │ /jobs/{id}   │◄─────────────┤ postgres_changes │        │
│  │              │              │ WebSocket        │        │
│  │              │              │                  │        │
│  │              │              │ jobs table       │        │
│  │ Job Manager  ├──────────────►                  │        │
│  │              │   INSERT/    │                  │        │
│  │              │   UPDATE     │                  │        │
│  └──────────────┘              └──────────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

## Comparison Logging

Phase 3.5 logs include:

**Job Status Comparison** (`useJobStatus` in `useOcrJob.ts:141-163`):
- SSE data: status, progress_pct, pages_completed
- Realtime data: status, progress_pct, pages_completed, latency, connected
- Match validation: status match, progress match, pages match

**Batch Status Comparison** (`useBatchJobStatus` in `useBatchJob.ts:96-109`):
- Realtime data: status, overall_progress_pct, documents_completed, total_documents
- Connection status and latency
- Error messages if any

## Next Steps

1. **Fix SystemMonitor.tsx** - Add null safety to allow frontend to load
2. **Test Phase 3.5** - Run manual test script and verify console logs
3. **Validate Latency** - Confirm WebSocket delivers updates faster than SSE
4. **Document Results** - Record actual latency measurements and match rates
5. **Phase 4 Planning** - Decide whether to migrate from SSE to Realtime or keep dual-subscription

## Files Modified/Created

### Created
- `web/lib/supabase.ts`
- `web/types/database.ts`
- `web/hooks/useRealtimeJob.ts`
- `web/hooks/useRealtimeBatch.ts`
- `test_realtime_simple.sh`

### Modified
- `web/hooks/useOcrJob.ts` (added dual-subscription to useJobStatus)
- `web/hooks/useBatchJob.ts` (added useBatchJobStatus export)
- `src/api/services/job_manager.py` (removed duplicate asyncio import)

### Needs Fix
- `web/components/SystemMonitor.tsx` (add null safety)

## Contact

For questions about Phase 3.5 implementation, testing, or results:
- Review comparison logs in browser console
- Check Supabase Realtime connection status
- Verify SSE polling interval in React Query DevTools

---

**Last Updated**: 2025-11-15
**Phase Status**: Implementation Complete, Testing Blocked
**Next Milestone**: Fix SystemMonitor.tsx, Run Manual Tests
