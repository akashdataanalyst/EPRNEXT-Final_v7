# Supplier Rejection UAT: JE25 OG

## Test Objective
Validate the supplier rejection flow for raw material `JE25 OG` with quantity `200 Kg`:

`Purchase Receipt -> Failed RM QC -> RM blocked for production use -> Purchase Return -> Debit Note`

## Record Summary
- Purchase Receipt: `MAT-PRE-2026-00013`
- Batch No: `RM-supplier-reject-JE25-OG-20260315142443`
- Failed Quality Inspection: `MAT-QA-2026-00072`
- RM Inward Validation: `1iaqd5mkus`
- RM QC Decision: `1ibga4s0hb`
- Purchase Return: `MAT-PRE-2026-00014`
- Debit Note: `ACC-PINV-2026-00004`

## Validation Summary
- Purchase Receipt created: `PASS`
- QC inspection marked failed/rejected: `PASS`
- RM blocked from production use without release: `PASS`
- Purchase Return submitted against receipt: `PASS`
- Debit Note created for supplier: `PASS`
- Stock ledger impact verified: `PASS`
- Supplier balance impact verified: `PASS`

## Key Evidence
- Purchase Receipt stock ledger:
  - `+200 Kg` into `Stores - CPPL`
- Purchase Return stock ledger:
  - `-200 Kg` from `Stores - CPPL`
- Failed QC link:
  - Reference Type: `Purchase Receipt`
  - Reference Name: `MAT-PRE-2026-00013`
  - Status: `Rejected`
- RM release status:
  - No submitted `RM Release Note` exists for the batch
- Production-use block observed:
  - `Released RM batch is missing for item JE25 OG, batch RM-supplier-reject-JE25-OG-20260315142443.`
- Debit Note impact:
  - Status: `Return`
  - Grand Total: `-200`
  - Supplier GL entry on `Creditors - CPPL`: `Debit 200`
