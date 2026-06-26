# Phase 3A Production Architecture Decision

## Final User-Facing Flow

Approved Phase 3A production flow:

1. `Production Requirement`
2. `Production Job Card`
3. `Material Availability & Batch Allocation`
4. `RM Requisition`
5. `Grade Change Clearance`
6. `Premix Preparation`
7. `Production Run`
8. `FG Delivery Note`
9. `FG Quarantine`

This is the only intended user-facing production path for Phase 3A.

## Work Order Decision

`Work Order` remains an internal ERPNext manufacturing dependency for now.

- It supports existing stock / manufacturing hooks already present in the app.
- It is not the primary production execution screen for business users.
- It should not be the main production navigation entry in the Production workspace.

Decision:

- `Work Order` is treated as backend / internal during Phase 3A transition.
- Production users should be guided through `Production Requirement` and `Production Job Card`.

## Material Readiness Check Decision

`Material Readiness Check` is a legacy / parallel readiness control tied to `Work Order`.

It overlaps with, but is not equal to, the approved `Material Availability & Batch Allocation` stage:

- `Material Readiness Check`
  - legacy gate on `Work Order`
  - simple readiness outcome: `Draft / Ready / Blocked`
  - checks BOM material availability against released RM

- `Material Availability & Batch Allocation`
  - approved Phase 3A stage on `Production Job Card`
  - user-facing execution step
  - performs FIFO batch allocation
  - supports partial availability and batch-level allocation outcomes

Decision:

- `Material Readiness Check` is not the future user-facing production stage.
- The approved user-facing equivalent is `Material Availability & Batch Allocation` on `Production Job Card`.
- No new business-facing production controls should be built on `Material Readiness Check` beyond transition support.

## Transition Rule

Until the Production Job Card flow is fully wired to backend manufacturing transactions:

- keep `Work Order` + `Material Readiness Check` only as internal compatibility controls
- keep their UX sufficient for support and UAT unblock
- do not expose them as the primary production route in the workspace
- continue building all new Phase 3A execution behavior on:
  - `Production Requirement`
  - `Production Job Card`
  - linked Phase 3A execution doctypes

## Coding Rule Going Forward

Before further Phase 3A coding:

- Use `Production Requirement` and `Production Job Card` as the source of truth for user flow.
- Treat `Work Order` as a backend mapped document, not a first-class production UI.
- Treat `Material Readiness Check` as a temporary legacy gate that should eventually be absorbed by the `Material Availability & Batch Allocation` stage.

## Workspace Guidance

Production workspace should prioritize:

- `Production Requirement`
- `Production Job Card`
- `Production RM Requisition`
- `Grade Change Clearance`
- `Premix Preparation`
- `FG Delivery Note`

It should not present `Work Order` as the normal first-step production path.
