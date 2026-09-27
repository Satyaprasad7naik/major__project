# Ontology Audit: Schema Consistency Report

**Verdict: No — the ontology (domain schema knowledge used by the NL2SQL agents) is not working correctly.** There are clear, material inconsistencies that will cause incorrect SQL generation.

## What "ontology" means here

In this project (InsightOS / DerivInsight), the ontology is the **domain-specific schema knowledge** that grounds the LLM agents. It lives primarily in:

- `app/data/domains/*.json` (especially the `schema_context`, `prompts.sql`, `prompts.intent`, `few_shots`, and `db_profile` sections)
- Supporting files: `app/files/derivinsight_schema.sql`, `actual_schema.json` / `actual_schema_fixed.json`, and notes in `KNOWLEDGE_TRANSFER.md`

These are what the Intent Classifier, SQL Generation Agent, and Sentinel use to map natural language → correct tables/columns/joins.

## Critical mismatches found

| Aspect | Domain JSONs (`risk.json`, `general.json`, etc.) + `derivinsight_schema.sql` | `actual_schema.json` / `actual_schema_fixed.json` | Impact |
|---|---|---|---|
| **users table** | `email`, `full_name`, `country`, `phone`, `date_of_birth`, `kyc_*`, `risk_*`, `is_pep`, `account_status` | `username`, `age`, `kyc_status`, `risk_*`, `is_pep`, `account_status` (no email / full_name / country / DOB) | Agents will generate queries for non-existent columns |
| **Email location** | SQL prompts say: "email is in the users table. You can select email directly from users.email." | Email only exists as `login_events.email_attempted` | Direct contradiction with `KNOWLEDGE_TRANSFER.md` ("Email data is in login_events.email_attempted (NOT in users table)") |
| **login_events** | Correctly has `email_attempted` in some places; one few-shot even uses it correctly | Matches | Partial correctness, but diluted by the users-table claim |
| **Few-shot examples** | Mix of correct and incorrect patterns (some use `u.full_name` / `u.email`, others correctly join for email) | N/A | Inconsistent training signal for the model |
| **Schema context text** | "exactly three tables: users, transactions, login_events" | Same three tables but different columns | Agents believe a schema that does not match the running DB (whichever one is actually loaded) |

## Additional problems visible in the domain files

- Typos and garbled text in prompts (e.g. `user_date_of_birthnt`, `mandate_of_birthment`).
- Conflicting rules inside the same prompt (e.g. "USE 'full_name' … NEVER use 'full_name'").
- `db_profile` sections contain sample unique values that match the richer schema, while `actual_schema*.json` reflects a different, simpler schema.
- Documentation (`KNOWLEDGE_TRANSFER.md`) explicitly calls out the email mapping as a critical rule that was "recently updated," yet the domain prompt files still contain the old (incorrect) claim.

## Practical consequence

When a user asks anything involving names, emails, geography, age, or KYC details, the SQL Generation Agent is likely to emit invalid SQL (unknown columns or wrong joins). The self-repair loop may catch some of these, but many will still fail or return wrong results. Sentinel missions are equally affected because they rely on the same domain configurations.

## Recommendation

1. Decide which schema is authoritative (the SQL file looks like the intended design; the `actual_schema*.json` files look like an older or alternate snapshot).
2. Synchronize **all** domain JSON files so that:
   - `schema_context` + SQL prompt column lists match the live database exactly.
   - Email rule is consistent everywhere (`login_events.email_attempted` if that is the reality, or `users.email` if the DB was updated).
   - Few-shots only use real columns.
3. Regenerate or delete the outdated `actual_schema*.json` files so they cannot confuse future work.
4. Add a simple schema-introspection check (or unit test) that fails the build if the domain prompts diverge from the live `PRAGMA table_info` / inspector output.

Until the domain JSONs, the SQL schema, and the running database are brought into exact agreement, the ontology cannot be considered working correctly.
