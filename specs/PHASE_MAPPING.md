# Phase Mapping: Old Structure → Unified Roadmap

**Purpose:** This document maps the old phase numbering system to the new unified roadmap structure.

**Date:** 2025-11-15

---

## Overview

The project originally had two parallel development tracks with overlapping phase numbers. This caused confusion (e.g., "Phase 3" in Supabase spec vs "Phase 3.5" in implementation). The unified roadmap consolidates these into a single coherent structure.

---

## Mapping Table

### BAML Integration Track

| Old Phase | Old Document | Unified Phase | New Document Section |
|-----------|--------------|---------------|---------------------|
| **BAML Phase 1** | [BAML_INTEGRATION_PHASE1.md](../archive/phases/BAML_INTEGRATION_PHASE1.md) | **Phase 1** | Foundation → BAML Track |
| **BAML Phase 2.1** | [BAML_INTEGRATION_PHASE2.md](../archive/phases/BAML_INTEGRATION_PHASE2.md) | **Phase 2** | Core Integration → BAML Track (2.1) |
| **BAML Phase 2.2** | [BAML_INTEGRATION_PHASE2.2_REVISED.md](../archive/phases/BAML_INTEGRATION_PHASE2.2_REVISED.md) | **Phase 2** | Core Integration → BAML Track (2.2) |
| **BAML Phase 2.3** | [PHASE_2_COMPLETE.md](../archive/phases/PHASE_2_COMPLETE.md) | **Phase 3** | Real-Time Infrastructure → BAML Track |

### Supabase Migration Track

| Old Phase | Old Document | Unified Phase | New Document Section |
|-----------|--------------|---------------|---------------------|
| **Supabase Phase 1** | [supabase-migration-spec.md](supabase-migration-spec.md) Phase 1 | **Phase 1** | Foundation → Supabase Track |
| **Supabase Phase 2** | [supabase-migration-spec.md](supabase-migration-spec.md) Phase 2 | **Phase 2** | Core Integration → Supabase Track |
| **Supabase Phase 3** | [supabase-migration-spec.md](supabase-migration-spec.md) Phase 3 | **Phase 3** | Real-Time Infrastructure → Supabase Track |
| **Supabase Phase 4** | [supabase-migration-spec.md](supabase-migration-spec.md) Phase 4 | **Phase 4** | Infrastructure Migration (Remove SSE) |
| **Supabase Phase 5** | [supabase-migration-spec.md](supabase-migration-spec.md) Phase 5 | **Phase 4** | Infrastructure Migration (Remove Memory) |
| **Supabase Phase 6** | [supabase-migration-spec.md](supabase-migration-spec.md) Phase 6 | **Phase 6** | Cloud Deployment |

### Implementation-Specific Documents

| Old Document | Status | Unified Phase | Notes |
|--------------|--------|---------------|-------|
| [PHASE_3.5_STATUS.md](../archive/phases/PHASE_3.5_STATUS.md) | ✅ Implementation complete | **Phase 3** | Realtime subscriptions - part of Supabase Phase 3 |
| [PHASE_3.5_TESTING_READY.md](../archive/phases/PHASE_3.5_TESTING_READY.md) | ⏳ Testing blocked | **Phase 3** | Dual-subscription testing |
| [PHASE_2.2_IMPLEMENTATION_COMPLETE.md](../archive/phases/PHASE_2.2_IMPLEMENTATION_COMPLETE.md) | ✅ Complete | **Phase 2** | Enhanced metadata |
| [PHASE_2_TESTING_REPORT.md](../archive/phases/PHASE_2_TESTING_REPORT.md) | ✅ Complete | **Phase 2** | Testing results |

---

## Detailed Phase Reconciliation

### Unified Phase 1: Foundation

**Consolidates:**
- BAML Phase 1 (type system, service layer)
- Supabase Phase 1 (local setup, schema, repositories)

**Why Combined:**
- Both are foundational infrastructure
- No dependencies on each other
- Can be implemented in parallel
- Both completed in same timeframe

**Result:** Single "Foundation" phase with two parallel tracks

---

### Unified Phase 2: Core Integration

**Consolidates:**
- BAML Phase 2.1 (pipeline integration)
- BAML Phase 2.2 (enhanced streaming metadata)
- Supabase Phase 2 (dual-write pattern)

**Why Combined:**
- All integrate new infrastructure into existing code
- All use additive changes (no breaking changes)
- BAML integration and dual-write are complementary
- Enhanced metadata works with both SSE and Realtime

**Result:** Single "Core Integration" phase with cohesive changes

---

### Unified Phase 3: Real-Time Infrastructure

**Consolidates:**
- BAML Phase 2.3 (frontend type sync)
- Supabase Phase 3 (Realtime subscriptions)
- Implementation "Phase 3.5" (dual-subscription monitoring)

**Why Combined:**
- Frontend type sync enables type-safe Realtime events
- Realtime subscriptions need BAML types
- "Phase 3.5" was actually implementing Supabase Phase 3
- All focus on real-time updates and frontend improvements

**Result:** Single "Real-Time Infrastructure" phase, eliminates "3.5" confusion

---

### Unified Phase 4: Infrastructure Migration

**Consolidates:**
- Supabase Phase 4 (remove SSE)
- Supabase Phase 5 (remove in-memory state)

**Why Combined:**
- Both remove old infrastructure
- Both are breaking changes requiring careful migration
- Best done together to minimize disruption
- Share similar testing requirements

**Result:** Single "Infrastructure Migration" phase

---

### Unified Phase 5: Production Readiness

**New Phase (Not in Original Specs)**

**Why Added:**
- Gap between "working" and "production-ready"
- Performance optimization needed
- Monitoring essential for production
- Security hardening required

**Content:**
- Performance optimization
- Monitoring and observability
- Error handling improvements
- Security audit
- Documentation

**Result:** Explicit production readiness phase

---

### Unified Phase 6: Cloud Deployment

**Matches:**
- Supabase Phase 6 (cloud deployment)

**Why Unchanged:**
- Already well-defined in original spec
- Clear deliverables and cost estimates
- No conflicts with BAML track

**Result:** Same as original Supabase Phase 6

---

## Status Translation

### Old Status Terms → New Status

| Old Status | New Status | Symbol |
|------------|------------|--------|
| "Complete" | ✅ COMPLETE | ✅ |
| "Implementation complete" | ✅ COMPLETE | ✅ |
| "Testing blocked" | 🔄 PARTIALLY COMPLETE | 🔄 |
| "Not started" | ⏳ PENDING | ⏳ |
| "Planning phase" | ⏳ PENDING | ⏳ |

---

## Benefits of Unified Structure

### 1. Eliminates Confusion

**Before:**
- "What's the difference between Phase 3 and Phase 3.5?"
- "Which Phase 2 are you talking about?"
- "Is BAML Phase 2.2 the same as Supabase Phase 2?"

**After:**
- Clear linear progression: Phase 1 → 2 → 3 → 4 → 5 → 6
- Each phase has clear objectives
- Sub-tracks (BAML/Supabase) clearly labeled

### 2. Shows Integration Points

**Before:**
- BAML and Supabase specs existed separately
- Unclear how they work together
- No visibility into dependencies

**After:**
- Each phase shows how BAML and Supabase integrate
- Clear type flow from BAML → Database → Frontend
- Dependencies explicitly documented

### 3. Single Source of Truth

**Before:**
- 8+ phase documents to track
- Conflicting information possible
- Hard to see overall progress

**After:**
- One master roadmap document
- All phase documents archived (reference only)
- Current status always clear

---

## How to Use This Mapping

### For Historical Reference

When reviewing old phase documents or git history:

1. Find the old phase number in document title
2. Look up in mapping table above
3. See corresponding unified phase
4. Read unified phase in [MASTER_ROADMAP.md](MASTER_ROADMAP.md)

**Example:**
- Find reference to "BAML Phase 2.2"
- Look up in table → Maps to "Unified Phase 2"
- Read Phase 2 section in master roadmap
- Find "BAML Track (Phase 2.2)" subsection

### For New Work

When planning new work:

1. Read only [MASTER_ROADMAP.md](MASTER_ROADMAP.md)
2. Ignore old phase documents (archived)
3. Use unified phase numbers in commits/PRs
4. Update implementation status document

**Example:**
- Working on Realtime testing
- Read "Phase 3: Real-Time Infrastructure" in master roadmap
- Use commit message: "feat(phase-3): fix SystemMonitor null safety"
- Update [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)

---

## Document Locations

### Active Documents (Use These)

- [specifications/MASTER_ROADMAP.md](MASTER_ROADMAP.md) - **Primary reference**
- [specifications/PHASE_MAPPING.md](PHASE_MAPPING.md) - This document (old → new mapping)
- [specifications/IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) - Current progress
- [specifications/supabase-migration-spec.md](supabase-migration-spec.md) - Detailed Supabase reference

### Archived Documents (Reference Only)

All archived documents moved to `archive/phases/`:

- `archive/phases/BAML_INTEGRATION_PHASE1.md`
- `archive/phases/BAML_INTEGRATION_PHASE2.md`
- `archive/phases/BAML_INTEGRATION_PHASE2.2_REVISED.md`
- `archive/phases/PHASE_2.2_IMPLEMENTATION_COMPLETE.md`
- `archive/phases/PHASE_2_COMPLETE.md`
- `archive/phases/PHASE_2_TESTING_REPORT.md`
- `archive/phases/PHASE_3.5_STATUS.md`
- `archive/phases/PHASE_3.5_TESTING_READY.md`

---

## Git Commit Conventions (New)

### Old Commit Style
```bash
# Confusing - which phase 2?
git commit -m "feat(phase-2): add BAML integration"
git commit -m "feat(phase-2): add dual-write"
git commit -m "feat(phase-3.5): add Realtime"
```

### New Commit Style
```bash
# Clear unified phases
git commit -m "feat(phase-1): BAML foundation"
git commit -m "feat(phase-2): dual-write pattern"
git commit -m "feat(phase-3): Realtime subscriptions"
git commit -m "fix(phase-3): SystemMonitor null safety"
```

---

## FAQ

### Q: Can I still reference old phase documents?

**A:** Yes, they're archived in `archive/phases/` for historical reference. But always use the master roadmap for current work.

### Q: What if I find a bug in an old phase?

**A:** Use the mapping to find the unified phase, then update the master roadmap and implementation status documents.

### Q: How do I know which phase to work on next?

**A:** Check [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for current phase status, then read the next pending phase in the master roadmap.

### Q: Should I update old phase documents?

**A:** No. Archive documents are frozen for historical reference. Update only the master roadmap and implementation status.

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-15 | Claude Code | Initial phase mapping document |

---

**END OF PHASE MAPPING**
