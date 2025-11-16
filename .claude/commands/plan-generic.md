---
description: Architecture-first implementation planning with explicit code-level interface boundaries, then derivation of swim lanes for parallel agents.
---

# Plan & Specification Command (Architecture-First, Code-Boundary Swim Lanes)

Design and plan **in this order** to minimize merge conflicts and refactors. Do not shape the architecture to fit the swim lanes; design the best architecture first, then derive swim lanes from it.

---

## A. Architectural Baseline & Component Catalog (Define First)

Produce a **post-implementation component catalog**:

1. **Files**
   - Exact paths (relative to repo root) that will be **added**, **modified**, or **removed**.
   - Prefer reusing existing files where practical.

2. **Classes / Types**
   - Names, locations, visibility.
   - Mark each as **new** or **modified**; avoid new types if extension is sufficient.

3. **Functions / Methods**
   - Names, locations, signatures:
     - Parameters (name, type, optionality)
     - Return type
     - Error behavior

4. **Data Structures**
   - DTOs, events, schemas, enums, config objects.
   - Exact fields and types, required vs optional, invariants, versioning behavior.

At this stage, do **not** assign swim lanes. Focus on designing the optimal architecture.

---

## B. Code-Level Interface Contracts (Freeze Before Build)

Define **code-level interface boundaries**. These are real code contracts, not just conceptual boxes.

For each interface:

- **Form**:
  - Public APIs (REST/GraphQL/RPC endpoints), including routes and handler symbols.
  - Public functions or methods (modules, classes).
  - Event topics and payload schemas.
  - DB contracts (tables/collections, views, queries, and migrations).

- **Contracts**:
  - Exact signatures and types.
  - Input/output structures and error behavior.
  - Invariants and idempotency where applicable.

- **Ownership**:
  - Identify which future swim lane will **own** the interface files.
  - Consumers must call these interfaces but not change their definitions within the phase.

- **Stability & Versioning**:
  - Decide whether interfaces are stable (no breaking changes this phase) or versioned.
  - Describe how breaking changes would be introduced (e.g., `v1` → `v2` endpoints).

- **Validation**:
  - Contract tests / schema validation / golden fixtures that must pass.

This step ends with an **interface freeze gate** (`IF-0`): no consumer work should proceed until these interfaces are defined and stable enough.

---

## C. Exhaustive Change List (Derived From A + B)

Turn A and B into a precise change list:

- For each file/class/function/data structure:
  - `Added | Modified | Removed`
  - Why it changes (link back to spec requirements and interfaces).
- Include:
  - Any migrations (data, config).
  - Feature flags or rollout/rollback controls if applicable.

This list is the **canonical source** of what will actually change in the repo.

---

## D. Swim-Lane Derivation (Fit to Architecture, Not Vice Versa)

Only after A–C are complete:

1. **Define Swim Lanes as Code-Ownership Boundaries**
   - Each lane has:
     - Name (e.g., `Ingestion Service`, `API Layer`, `Web UI`, `Persistence`, `Observability`).
     - Responsibilities.
   - Assign **ownership**:
     - Exact files and symbols each lane is allowed to edit.
     - Try to ensure each file is owned by a single lane for this phase.

2. **Non-Overlapping Code Boundaries**
   - Consumers may use public interfaces from other lanes’ modules but may **not** edit those interface definition files.
   - If a file must be touched by multiple lanes:
     - Call this out explicitly.
     - Define sequencing or scoped regions to minimize merge conflicts.

3. **Parallelization Plan**
   - For each lane:
     - List tasks, with the files/symbols they modify.
     - Mark tasks that can run in parallel once `IF-0` is satisfied.
     - Mark tasks that require ordered sequencing due to shared files or interfaces.

Swim lanes must **fit the architecture and interfaces**—never the other way around.

---

## E. Work Packages & Sequencing

For each swim lane:

- Define **work packages**:
  - Tasks with clear goals.
  - Exact files and symbols touched.
  - Dependencies on:
    - Interface freeze (`IF-0`).
    - Other lanes’ outputs.

- Highlight:
  - Tasks safe for fully parallel execution (no overlapping file edits).
  - Tasks that must be serialized.

---

## F. File-by-File Specification

For every file in the change list:

- `path/to/file.ext` — **[new|modified|removed]** — **Owner lane**: `<lane-name or shared>`
  - List classes/functions/data structures:
    - **Purpose** (1–3 sentences).
    - **Signature**:
      - Parameters (name, type, optionality).
      - Return type.
      - Exceptions / error states.
    - **Side effects**:
      - I/O, DB, network, cache, events.
    - **Interface participation**:
      - Which interfaces it implements or calls.

This section must be detailed enough for an engineer to implement without re-reading the spec.

---

## G. Data Structures & Schemas

List all affected data structures:

- Fields, types, required/optional.
- Invariants, versioning strategy.
- Producer lane vs consumer lanes.
- Migration steps and backward-compat notes.

---

## H. Execution Flow

Describe the runtime flow:

- Step-by-step sequence from external trigger(s) → internal processing → side effects.
- For each step:
  - Responsible file/module and symbol.
  - Interface boundaries crossed.

---

## I. Merge-Conflict Minimization Controls

- Ownership:
  - Use path-based ownership (e.g., CODEOWNERS) to bind interface files to specific lanes.
- CI:
  - Interface/signature drift checks.
  - Contract tests must pass before merge.
- Branching:
  - Interface PRs merged early.
  - Short-lived feature branches aligned to swim-lane ownership.

---

## J. Acceptance Criteria

- Architectural catalog (A) complete and coherent.
- Interfaces (B) defined and frozen (`IF-0`).
- Change list (C) exhaustive and consistent.
- Swim lanes (D) respect architecture, not vice versa.
- Work packages (E–H) enable high parallelism with minimal overlapping edits.

Your task: apply this template to the current system/spec and produce the full plan in order A→J.
