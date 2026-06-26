# Purchase UAT Report: JE25 OG

## Test Objective
Validate the raw-material procurement workflow in the live ERP for `JE25 OG` with quantity `1000 Kg`:

`Supplier -> Purchase Order -> Purchase Receipt -> Batch creation -> RM Quality Inspection -> RM Release -> Purchase Invoice -> Payment Entry`

## Test Item
- Item: `JE25 OG`
- Quantity: `1000 Kg`
- Supplier: `Test RM Supplier`

## Record Summary
- Purchase Order: `PUR-ORD-2026-00003`
- Purchase Receipt: `MAT-PRE-2026-00012`
- Batch No: `RM-purchase-uat-JE25-OG-20260315141552`
- Quality Inspection: `MAT-QA-2026-00071`
- RM Inward Validation: `sc83eg3hef`
- RM QC Decision: `sc9a5jrg1g`
- RM Release Note: `sc952uc0kc`
- Purchase Invoice: `ACC-PINV-2026-00003`
- Payment Entry: `ACC-PAY-2026-00003`

## Validation Summary
- Purchase Order creation: `PASS`
- Purchase Receipt and stock update: `PASS`
- Batch creation: `PASS`
- RM Quality Inspection linked to Purchase Receipt: `PASS`
- RM Release creation: `PASS`
- RM Release required before production use: `PASS`
- Purchase Invoice linked to Purchase Receipt: `PASS`
- Payment Entry closed invoice: `PASS`

## Key Evidence
- Stock Ledger after Purchase Receipt:
  - Item: `JE25 OG`
  - Warehouse: `Stores - CPPL`
  - Actual Qty: `1000`
  - Stock Value Difference: `1000`
- Quality Inspection link:
  - Reference Type: `Purchase Receipt`
  - Reference Name: `MAT-PRE-2026-00012`
  - Status: `Accepted`
- Purchase Invoice status after payment:
  - Status: `Paid`
  - Outstanding Amount: `0`

## RM Release Gate Check
Attempted production-use stock entry before RM release.

Observed block:
`Released RM batch is missing for item JE25 OG, batch RM-purchase-uat-JE25-OG-20260315141552.`

Result: `PASS`
