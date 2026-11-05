# Cost Report

CAFIITK-191. This report checks two requirements:

- **NFR-43:** cloud resources stay within the AWS free tier, with a billing alarm at USD 1.
- **NFR-42:** LLM usage stays within P-AGENT_DAILY_CAP requests a day and USD 5 a month.

The deployment it describes is CAFIITK-190; see `deploy/README.md`.

## 1. AWS account and plan

The account was created in November 2026 on the AWS **Free plan**. Under this plan, usage is paid only from the sign-up credit (USD 100). The account cannot incur charges: when the credit or the six-month period runs out, the account closes instead of billing the card. Upgrading to the Paid plan is a deliberate console action, and nobody has taken it.

The Billing page showed the following when the account was created:

- Current plan: **Free**
- Amount due: **USD 0.00**
- Credits remaining: **USD 100.00**
- Days remaining: **182**, until 5 May 2027

## 2. Resources and free-tier eligibility

Region `ap-southeast-2` (Sydney). Instance type, availability zone and disk size were read from the EC2 instance; PostgreSQL version, database size and private-only access from RDS itself. Items marked † are from the console setup and are confirmed by the screenshots in §3–§4.

| Resource | Configuration | Free tier |
|---|---|---|
| EC2 `caf-server` | `t3.small`, 8 GB gp3, Ubuntu 24.04 | `t3.small` is marked free-tier eligible for accounts created on or after 15 Jul 2025; gp3 is an eligible volume type |
| RDS `caf-db` | PostgreSQL 16.15, `db.t4g.micro`†, Single-AZ†, not public; database 9 MB | Free tier template; no Multi-AZ, Provisioned IOPS or Extended Support |
| Elastic IP | One, attached to `caf-server` | Public IPv4 is charged hourly and drawn from the credit |
| CloudFront | One distribution, caching disabled | Free pricing plan† |
| Data transfer | Demo traffic only | Within the free allowance |

**Nothing outside the free plan is used.** The following are all absent:

- NAT gateway
- load balancer
- Multi-AZ
- Savings Plans
- Reserved Instances
- Marketplace products

## 3. Billing alarm (USD 1)

An AWS Budgets cost budget of USD 1 a month, with an email alert.

> **Pending evidence:** a screenshot of the budget (Billing → Budgets) showing the USD 1 amount and the alert recipient.

## 4. Credit consumption

> **Pending evidence:** month-to-date usage and credits remaining from the Billing page, recorded after the stack has run for at least a day.

The deployment is due to be torn down after the demo (8–13 Nov 2026), as listed in `deploy/README.md`.

## 5. LLM usage and spend (NFR-42)

### Enforcement

`llm.consume_daily_budget` counts every provider request in `rate_limits` before it is made. Once P-AGENT_DAILY_CAP (50) is reached, the agent falls back to the heuristic planner (FR-59). `test_llm_client.py` covers this, including concurrent processes.

Two further guards avoid repeat calls:

- an identical request on the same IST day is answered from a cache;
- a circuit breaker stops calls after repeated failures.

### Report

`python -m app.modules.agent.spend [--month YYYY-MM]` reports the following for each IST day:

- billed requests
- cached answers
- errors
- input and output tokens
- cost in USD at OpenAI list prices: `gpt-4o-mini`, USD 0.15 per million input tokens and USD 0.60 per million output tokens

It ends with the busiest day against the cap and the month's total against USD 5. It exits with status 1 in three cases:

- the month is over budget;
- a day is over the cap;
- a model has no price. An unpriced model is reported, not counted as free.

**Run on the deployed stack, November 2026:**

```
LLM spend for November 2026 (IST days)

Day           Billed  Cached  Errors   In tokens  Out tokens       USD
2026-11-06         0       0       1           0           0    0.0000

Busiest day: 0 billed requests (P-AGENT_DAILY_CAP 50)
Month total: USD 0.0000 of USD 5
Within NFR-42
```

No LLM API key is configured on the deployment, so every agent run so far has used the heuristic planner. The one error row is the attempted LLM request of the single agent run.

### Worst case

The cap allows at most 50 × 31 = 1,550 billed requests a month. The month stays under USD 5 as long as the average request costs under USD 5 / 1,550 ≈ USD 0.0032. For example, 16,000 input and 1,000 output tokens per request cost USD 0.0030 at `gpt-4o-mini` prices.

If a key is added, run the report after the first LLM runs and check the actual tokens per request against this bound.

## 6. Status

| Requirement | Status |
|---|---|
| NFR-43 free tier | Met by construction (Free plan, eligible resources); credit consumption pending (§4) |
| NFR-43 USD 1 alarm | Pending evidence (§3) |
| NFR-42 daily cap | Enforced and tested (`test_llm_client.py`) |
| NFR-42 monthly spend | Reported: USD 0 in November 2026; worst case bounded as in §5 |
