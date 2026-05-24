export const EXTERNAL_AI_EXPORT_PROMPT = `You are helping me set up a personal budgeting app called "Pocket Buddy" (Indian user, INR only).

Go through our entire conversation history and extract everything financial you know about me. Output a single raw JSON object — no markdown, no explanation, just the JSON.

Use this exact structure:

{
  "profile": {
    "salary_day_of_month": <1–31 or null>,
    "monthly_rent_inr": <number or null>,
    "daily_budget_inr": <my typical daily variable spend limit, or null>,
    "wallets": [
      { "id": 1, "label": "<bank/UPI name>", "balance_inr": <current balance> }
    ]
  },
  "recurring": [
    {
      "item": "<name e.g. Netflix, EMI, Maid>",
      "amount_inr": <number>,
      "cadence": "<monthly | weekly | yearly>",
      "note": "<e.g. deducted on 5th, or empty string>"
    }
  ],
  "expenses": [
    {
      "date": "<YYYY-MM-DD or unknown>",
      "description": "<what was spent on>",
      "amount_inr": <number>,
      "category": "<food | cab | rent | emi | electricity | subscription | shopping | medical | misc>"
    }
  ]
}

Rules:
- INR only. Never invent numbers — if unsure, use null or omit the item.
- wallets: one entry per bank/wallet I mentioned. id=1 = my primary spending account.
- recurring: fixed monthly costs (rent, maid, subscriptions, EMIs, etc.)
- expenses: every individual spend I mentioned, one row per transaction.
- If I mentioned a range, use the midpoint and add "(approx)" in description.
- Output ONLY the JSON. Nothing else before or after.`;
