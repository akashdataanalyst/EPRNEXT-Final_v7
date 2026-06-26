# Purchase Commercial Approval UAT

- Generated On: `2026-06-08 22:48:14.177235`

## Benchmark Proof

- `CA-LAST-20260608224810-commercial-approval`: source `Last Purchase Rate`, rate `88.0`, reference `CA-LAST-20260608224810-commercial-approval`
- `CA-AVG-20260608224810-commercial-approval`: source `Last Purchase Rate`, rate `90.0`, reference `CA-AVG-20260608224810-commercial-approval`
- `CA-BELOW-20260608224810-commercial-approval`: source `Item Standard Buying Rate`, rate `100.0`, reference `CA-BELOW-20260608224810-commercial-approval`
- `CA-MISS-20260608224810-commercial-approval`: source `Missing`, rate `None`, reference `-`

## Test Documents

- `Below Benchmark`: Supplier Quotation `PUR-SQTN-2026-00016`, Commercial Approval `-`, Purchase Order `PUR-ORD-2026-00064`
- `Equal Benchmark`: Supplier Quotation `PUR-SQTN-2026-00017`, Commercial Approval `-`, Purchase Order `PUR-ORD-2026-00065`
- `Above Benchmark Approved`: Supplier Quotation `PUR-SQTN-2026-00018`, Commercial Approval `fam4iemiqn`, Purchase Order `PUR-ORD-2026-00067`
- `Above Benchmark Rejected`: Supplier Quotation `PUR-SQTN-2026-00019`, Commercial Approval `faqc9e5l07`, Purchase Order `-`
- `Missing Benchmark`: Supplier Quotation `PUR-SQTN-2026-00020`, Commercial Approval `fasbmfb8uk`, Purchase Order `-`

## PASS / FAIL

| Test | Result | Notes |
| --- | --- | --- |
| 1. SQ rate below benchmark | PASS | Approval docs: 0; PO: PUR-ORD-2026-00064 |
| 2. SQ rate equal benchmark | PASS | Approval docs: 0; PO: PUR-ORD-2026-00065 |
| 3. SQ rate above benchmark | PASS | Approval: fam4iemiqn; blocked message: Commercial Approval is required because quoted rate is higher than benchmark.<br><br>CA-ABV-APP-20260608224810-commercial-approval (Commercial Approval Above Approve) in PUR-SQTN-2026-00018: quoted ₹ 120.00 vs benchmark ₹ 100.00 from Item Standard Buying Rate; approval status Draft [fam4iemiqn] |
| 4. Approval approved | PASS | PO after approval: PUR-ORD-2026-00067 |
| 5. Approval rejected | PASS | Approval: faqc9e5l07; blocked message: Commercial Approval is required because quoted rate is higher than benchmark.<br><br>CA-ABV-REJ-20260608224810-commercial-approval (Commercial Approval Above Reject) in PUR-SQTN-2026-00019: quoted ₹ 125.00 vs benchmark ₹ 100.00 from Item Standard Buying Rate; approval status Rejected [faqc9e5l07] |
| 6. Benchmark missing | PASS | Approval: fasbmfb8uk; blocked message: Commercial Approval is required because benchmark rate is missing.<br><br>CA-MISS-20260608224810-commercial-approval (Commercial Approval Missing) in PUR-SQTN-2026-00020: benchmark rate is missing; approval status Draft [fasbmfb8uk] |