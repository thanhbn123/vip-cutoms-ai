# Acceptance Criteria

## Product acceptance

A test case with Invoice + Packing List must be able to:

1. create a case;
2. upload files;
3. extract and display structured fields;
4. show source/confidence for extracted values;
5. detect a deliberate Invoice/Packing discrepancy;
6. create goods items;
7. propose an HS candidate;
8. block a low-evidence critical classification;
9. allow reviewer approval/rejection with reason;
10. generate a versioned declaration draft;
11. preserve audit history;
12. answer case-scoped Copilot questions without inventing missing facts.

## Security acceptance

- cross-tenant reads forbidden and tested;
- all critical writes authorized server-side;
- no secrets committed;
- uploaded documents are private by default;
- audit records exist for critical decisions;
- AI provider output is validated before persistence.

## Quality acceptance

- migrations have one current head;
- unit/integration tests pass on PostgreSQL;
- browser E2E covers the primary case;
- seed/demo tariff and policy data are visibly labeled as non-authoritative;
- no production customs submission occurs during MVP/staging acceptance.
