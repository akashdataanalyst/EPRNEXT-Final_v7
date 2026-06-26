# Purchase Commercial Approval UAT

- Generated On: `2026-06-08 22:57:13.759239`

## Benchmark Proof

- `CA-LAST-20260608225710-commercial-approval`: source `Last Purchase Rate`, rate `88.0`, reference `CA-LAST-20260608225710-commercial-approval`
- `CA-AVG-20260608225710-commercial-approval`: source `Average of Last 3 Purchase Orders`, rate `80.0`, reference `PUR-ORD-2026-00072, PUR-ORD-2026-00071, PUR-ORD-2026-00070`
- `CA-BELOW-20260608225710-commercial-approval`: source `Item Standard Buying Rate`, rate `100.0`, reference `CA-BELOW-20260608225710-commercial-approval`
- `CA-MISS-20260608225710-commercial-approval`: source `Missing`, rate `None`, reference `-`

## Test Documents

- `Below Benchmark`: Supplier Quotation `PUR-SQTN-2026-00021`, Commercial Approval `-`, Purchase Order `PUR-ORD-2026-00073`
- `Equal Benchmark`: Supplier Quotation `PUR-SQTN-2026-00022`, Commercial Approval `-`, Purchase Order `PUR-ORD-2026-00074`
- `Above Benchmark Approved`: Supplier Quotation `PUR-SQTN-2026-00023`, Commercial Approval `kjacb0dk10`, Purchase Order `PUR-ORD-2026-00076`
- `Above Benchmark Rejected`: Supplier Quotation `PUR-SQTN-2026-00024`, Commercial Approval `kjebcr6g82`, Purchase Order `-`
- `Missing Benchmark`: Supplier Quotation `PUR-SQTN-2026-00025`, Commercial Approval `kjgclhguhc`, Purchase Order `-`

## PASS / FAIL

| Test | Result | Notes |
| --- | --- | --- |
| 1. SQ rate below benchmark | PASS | Approval docs: 0; PO: PUR-ORD-2026-00073 |
| 2. SQ rate equal benchmark | PASS | Approval docs: 0; PO: PUR-ORD-2026-00074 |
| 3. SQ rate above benchmark | PASS | Approval: kjacb0dk10; blocked message: Commercial Approval is required because quoted rate is higher than benchmark.<br><br>CA-ABV-APP-20260608225710-commercial-approval (Commercial Approval Above Approve) in PUR-SQTN-2026-00023: quoted ₹ 120.00 vs benchmark ₹ 100.00 from Item Standard Buying Rate; approval status Draft [kjacb0dk10] |
| 4. Approval approved | PASS | PO after approval: PUR-ORD-2026-00076 |
| 5. Approval rejected | PASS | Approval: kjebcr6g82; blocked message: Commercial Approval is required because quoted rate is higher than benchmark.<br><br>CA-ABV-REJ-20260608225710-commercial-approval (Commercial Approval Above Reject) in PUR-SQTN-2026-00024: quoted ₹ 125.00 vs benchmark ₹ 100.00 from Item Standard Buying Rate; approval status Rejected [kjebcr6g82] |
| 6. Benchmark missing | PASS | Approval: kjgclhguhc; blocked message: Commercial Approval is required because benchmark rate is missing.<br><br>CA-MISS-20260608225710-commercial-approval (Commercial Approval Missing) in PUR-SQTN-2026-00025: benchmark rate is missing; approval status Draft [kjgclhguhc] |