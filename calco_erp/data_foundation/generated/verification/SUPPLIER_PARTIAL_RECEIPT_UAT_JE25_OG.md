# Supplier Partial Receipt UAT: JE25 OG

## Test Objective
Validate the partial supplier receipt flow for `JE25 OG` with:

- Purchase Order Qty: `1000 Kg`
- Actual Received Qty: `700 Kg`

## Record Summary
- Purchase Order: `PUR-ORD-2026-00004`
- Purchase Receipt: `MAT-PRE-2026-00015`
- Batch No: `RM-partial-receipt-JE25-OG-20260315142938`
- Quality Inspection: `MAT-QA-2026-00073`
- RM Inward Validation: `4eafdoe9d6`
- RM QC Decision: `4eaan4n1cf`
- RM Release Note: `4eap5hhjdc`

## Validation Summary
- Purchase Order created for `1000 Kg`: `PASS`
- Purchase Receipt posted for only `700 Kg`: `PASS`
- Purchase Order pending balance remained open at `300 Kg`: `PASS`
- QC completed on received quantity: `PASS`
- RM Release created only for the received batch and quantity: `PASS`
- Stock ledger updated for received quantity: `PASS`
- PO balance status updated correctly: `PASS`

## Key Evidence
- PO status after receipt:
  - Status: `To Receive and Bill`
  - Received: `700 Kg`
  - Pending: `300 Kg`
  - Per Received: `70%`
- Quality Inspection:
  - Reference Name: `MAT-PRE-2026-00015`
  - Status: `Accepted`
- RM Release:
  - Batch: `RM-partial-receipt-JE25-OG-20260315142938`
  - Release Qty: `700 Kg`
  - Status: `Released`
- Stock Ledger on Purchase Receipt:
  - `+700 Kg` into `Stores - CPPL`
