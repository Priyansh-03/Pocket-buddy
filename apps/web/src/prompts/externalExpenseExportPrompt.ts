/**
 * Copy this into ChatGPT (or any AI) so it emits a structured block you can paste
 * back into Survival's Money & savings or main chat for onboarding / tuning.
 */
export const EXTERNAL_AI_EXPORT_PROMPT = `You are helping me export financial facts for a budgeting app called "Financial Survival Assistant". Everything must be in Indian Rupees (INR) only.

Your job
1) If you already remember, from our past messages together, my recurring bills, subscriptions, loans/EMIs, salary timing, rent, approximate bank/UPI balance, savings goals, and/or itemized spends: produce ONE structured export using ONLY what I actually told you. Never invent precise numbers.
2) If you do NOT have enough information, ask the smallest clear set of follow-up questions (salary day-of-month 1–31, monthly rent or other big fixed costs, rough liquid cash now, major recurring charges, and any expenses I have mentioned). After I answer, produce the export.

Strict output format — use these exact markers and section headers, in order:

---BEGIN_EXPORT---
PROFILE
- salary_day_of_month: <1-31 or unknown>
- monthly_rent_or_fixed_inr: <number or unknown>
- estimated_liquid_cash_inr: <number or unknown>
- notes: <short bullets: EMIs, family support, goals, habits — or "unknown">

RECURRING
| item | amount_inr | cadence | note |
(One markdown table row per line. If nothing known: one row with "unknown" in item.)

RECENT_EXPENSES
| date_or_unknown | description | amount_inr | category_guess |
(One markdown table row per line. If nothing known: one row with "unknown" in description.)

ASSUMPTIONS
- <bullet list of anything approximate or inferred; if none, write a single bullet "none">

---END_EXPORT---

Rules
- INR only; no other currencies.
- If I gave a range, use one number and add "(approx from range)" in the note or description column.
- Keep prose outside the export minimal; the block between ---BEGIN_EXPORT--- and ---END_EXPORT--- should be paste-ready.`;
