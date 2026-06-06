# Receipt Variance UAT: JE25 OG

## Test Objective
Validate receipt variance behavior for `JE25 OG` against a `1000 Kg` Purchase Order:

- Under receipt: `700 Kg`
- Over receipt: `1100 Kg`

## Live Configuration
- Stock Settings Over Receipt/Delivery Allowance: `0%`
- Item Over Receipt/Delivery Allowance: `0%`

## Under Receipt Result
- Purchase Order: `PUR-ORD-2026-00005`
- Purchase Receipt: `MAT-PRE-2026-00016`
- Quality Inspection: `MAT-QA-2026-00074`
- Batch: `RM-under-receipt-under-20260315144050`
- Result: `PASS`

### Verified
- ERP allowed receipt of `700 Kg`: `PASS`
- PO remained open for pending quantity: `PASS`
- Pending Qty on PO: `300 Kg`
- PO Status: `To Receive and Bill`
- Stock Ledger impact: `+700 Kg` into `Stores - CPPL`
- Accounting impact:
  - Debit `Stock In Hand - CPPL` `700`
  - Credit `Stock Received But Not Billed - CPPL` `700`

## Over Receipt Result
- Purchase Order: `PUR-ORD-2026-00006`
- Attempted Purchase Receipt: `MAT-PRE-2026-00017`
- Quality Inspection: `MAT-QA-2026-00075`
- Batch: `RM-over-receipt-over-20260315144050`
- Result: `PASS`

### Verified
- ERP blocked receipt of `1100 Kg`: `PASS`
- Block reason:
  - `This document is over limit by Qty 100.0 for item JE25 OG.`
- PO remained unchanged:
  - Received Qty: `0 Kg`
  - Pending Qty: `1000 Kg`
  - PO Status: `To Receive and Bill`
- Stock impact: `None`
- Accounting impact: `None`
