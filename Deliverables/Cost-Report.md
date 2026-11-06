# Cost Report

CAFIITK-191. This report checks two requirements:

- **NFR-43:** cloud resources stay within the AWS free tier, with a billing alarm at USD 1.
- **NFR-42:** LLM usage stays within P-AGENT_DAILY_CAP requests a day and USD 5 a month.

The deployment it describes is CAFIITK-190; see `deploy/README.md`. Figures are as of 6 November 2026, the day after deployment.

## 1. AWS account and plan

The account was created on 5 November 2026 on the AWS **Free plan**. Under this plan, usage is paid only from credits. The account cannot incur charges: when the credits or the six-month period run out, the account closes instead of billing the card. Upgrading to the Paid plan is a deliberate console action, and nobody has taken it.

**Billing page:**

- Current plan: Free
- Amount due: USD 0.00
- Days remaining: 182, until 5 May 2027
- Credits remaining: **USD 140.00**

**Credits:**

| Credit | Issued | Used | Expires |
|---|---|---|---|
| AWS Free Tier | USD 100.00 | USD 0.00 | 5 Nov 2027 |
| Explore AWS: set up a cost budget using AWS Budgets | USD 20.00 | USD 0.00 | 5 Nov 2027 |
| Explore AWS: create an Aurora or RDS database | USD 20.00 | USD 0.00 | 5 Nov 2027 |

AWS updates the estimated amounts about every 24 hours, so the first day's usage had not appeared yet.

## 2. Resources and free-tier eligibility

Region `ap-southeast-2` (Sydney). Sources:

- EC2: the instance metadata.
- RDS: its Configuration page and the database itself.
- CloudFront: its distribution page.

| Resource | Configuration | Free tier |
|---|---|---|
| EC2 `caf-server` | `t3.small` in `ap-southeast-2b`, 8 GB gp3, Ubuntu 24.04 | `t3.small` is marked free-tier eligible for accounts created on or after 15 Jul 2025; gp3 is an eligible volume type |
| RDS `caf-db` | PostgreSQL 16.15, `db.t4g.micro` in `ap-southeast-2c`, Multi-AZ no, 20 GiB gp3 (autoscaling off), encrypted, not public; RDS Extended Support disabled; Enhanced Monitoring disabled; database 9 MB | Created from the Free tier template; none of the billable options (Multi-AZ, Provisioned IOPS storage, Extended Support) |
| Elastic IP | One, attached to `caf-server` | Public IPv4 is charged hourly and paid from the credits |
| CloudFront `caf-iitk-production` | One distribution, caching disabled | Well within CloudFront's always-free monthly allowance; any usage is paid from the credits |
| Data transfer | Demo traffic; EC2 to RDS crosses availability zones (2b to 2c) | A few MB a day, paid from the credits |

**Nothing outside the free plan is used.** The following are all absent:

- NAT gateway
- load balancer
- Multi-AZ
- Savings Plans
- Reserved Instances
- Marketplace products

**CloudFront pricing plan.** The console reports "Missing permissions" for the distribution's pricing plan, because the console role lacks `PricingPlanManagerReadonlyAccess`. Whatever the plan, the Free account plan cannot be billed.

## 3. Billing alarm (USD 1)

AWS Budgets → `CAFIITK-Monthly-Budget`:

| Field | Value |
|---|---|
| Budget type | Cost budget |
| Amount and period | USD 1.00, monthly, from 1 Nov 2026 |
| Alert | Actual cost > 100 % (USD 1), by email to a team member |
| Health | Healthy: USD 0.00 of USD 1.00 spent |

The recipient's email address has not been verified; AWS requires this, for recipients added after 30 September 2026, before it delivers alerts. The team decided not to verify it, because the Free account plan cannot be billed whatever the alarm does, so an alert would never require any action. Cost is checked on the Billing page instead (§4).

## 4. Credit consumption

On 6 November 2026, the day after deployment, total credits used were USD 0.00 of USD 140.00. AWS had not yet posted the first day's usage, and month-to-date cost showed no data.

The stack runs only for the demo period (8–13 Nov 2026) and is then torn down, as listed in `deploy/README.md`.

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
| NFR-43 free tier | Met: Free account plan (cannot be billed), free-tier resources, USD 0.00 of USD 140.00 credits used |
| NFR-43 USD 1 alarm | Met: USD 1 monthly cost budget configured (§3) |
| NFR-42 daily cap | Enforced and tested (`test_llm_client.py`) |
| NFR-42 monthly spend | Reported: USD 0 in November 2026; worst case bounded as in §5 |
