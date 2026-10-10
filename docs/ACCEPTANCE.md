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
- AI provider output is validated before persistence;
- login is tenant-aware: the same e-mail may exist in several tenants, an unauthenticated caller cannot learn in which
  tenants an e-mail exists (generic 401 for wrong password, wrong or unknown tenant code), and a tenant ADMIN cannot
  probe other tenants' e-mails through user creation;
- account lifecycle (create, re-role, deactivate/reactivate, password reset, self-service password change) is tenant-
  scoped, needs a reason, is audited, and an ADMIN can never lock themselves out;
- every token issued before a password change or reset is void; a deactivated account's tokens stop working at once;
- repeated failed logins are throttled (429 + Retry-After) before any password hashing;
- the tenant's audit trail (accounts, lockouts, knowledge) is readable in the product, not only per case.

## Quality acceptance

- migrations have one current head;
- unit/integration tests pass on PostgreSQL;
- browser E2E covers the primary case, tenant-code login and the account lifecycle, and runs in CI;
- seed/demo tariff and policy data are visibly labeled as non-authoritative;
- no production customs submission occurs during MVP/staging acceptance.
