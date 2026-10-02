# Post-publication advertising and KDP monitoring

Use the shared author/project and existing connector, report importer and monitor. Offer the next step after publication; do not end the journey at uploading files. Submitted, approved and live are different states. Verify the chosen edition's public listing and current advertising eligibility before launching. Check Author Central requirements in current official guidance and the actual account.

## Start with an affordable experiment

Explain briefly what an ad test can teach and ask for missing investment limits: total test budget/currency and period, daily setting, maximum bid, marketplace/format/ASIN, and whether the user wants guidance or execution. A prior scoped budget remains valid; do not ask again unnecessarily. Zero budget is valid: improve listing/sample, author presence and ethical reader discovery without inventing free sales.

Read current actual per-format royalty/receipt economics. Retail sales in an advertising report are not money in the author's bank. Account for printing/delivery already deducted, refunds, attribution differences and other costs without double counting. Do not copy generic $20/$50 pause thresholds, minimum review counts, $3–5 daily budgets or a fixed two-week maturity rule from another skill. Establish the experiment's loss tolerance, learning question, actual reporting window and conversion uncertainty. No guaranteed profitable CPC or title count follows from an income goal.

## Choose an actual access route

1. Inspect current host tools and `connect inspect`. For direct Amazon API use, help configure the documented local environment and OAuth process, discover real profiles, select the correct account/region/currency/timezone and perform a read-only query. API access requires Amazon's application/approval process; an ordinary KDP login does not grant it. Never ask for raw secrets in chat.
2. If the owner has an authorized Ads MCP, inspect its actual schema, provider, permissions, data exposure and account identity. Use only returned tools. A “recommendations” tool does not imply campaign mutation or scheduling. No mandatory Marketplace Ad Pros account, hosted MCP, BookBeam or paid service is introduced.
3. With no API/MCP, use the signed-in normal browser for attended controls when available and authorized. Otherwise guide the observed console screens and accept actual exported reports through `report-import`/`ads-analyze`. Tell the owner which actions still require them; an import route is not an autonomous background connection.

## Prepare, run and reconcile

Use observed reader searches and relevant comparable ASINs as targeting hypotheses; paid targeting and backend listing keywords have different rules. Keep campaigns/targets distinct by account, marketplace, book edition, campaign, ad group and match type. Automatic discovery can be offered only through a route that actually supports it. The bundled connector supports its documented Sponsored Products keyword/product targets; do not invent demographics, age selection, unsupported ad formats or a retail search-volume API.

Prepare the exact campaign, dates, daily setting, bids, targeting/match types, negatives and creative/listing details. Explain the amount at risk and current platform budget behavior. A daily budget is not a strict day-by-day ceiling, and delayed reports prevent a guaranteed exact stop amount. Account settings and current help must be inspected; do not hardcode an overdelivery percentage from conflicting/localized guidance.

Use the existing `connect ads prepare-campaign` / `execute-campaign` contract in reference 21: scoped connector approval, paused assembly, exact dependent IDs, readback and optional authorized activation. Reuse valid authorization within its scope. Budget increases, new targets or broader actions outside it need a new concrete approval. Reconcile unknown outcomes before retrying. Record actual receipts and live state; a successful preparation is not a launched ad.

## Analyze and manage performance

`ads-analyze` requires an authorized, reconciled report with period, currency, selected title/format, attribution basis and actual mapped columns. Add `group_columns` mapping any available `campaign_id`, `ad_group_id`, `target_id`, `match_type`, `placement`, `advertised_asin` to their real CSV headers. Map identity-bearing columns before combining rows. Without identifiers, output is an aggregate for review, not a verified entity to mutate. Same wording across campaigns/matches must remain separate.

Inspect spend, impressions, clicks, CTR, CPC, orders, observed order rate, retail ACoS/ROAS and royalty-based contribution/break-even scenarios. Ratios are fractions, not already percentages; null denominators remain unknown. Order counts are not always units or attributable royalty receipts. Use one format/title basis or split reports. Unknown royalties require economic review; a good retail ROAS alone cannot justify scaling.

- Few/no impressions: inspect live eligibility, index/relevance and actual bids/auction availability; do not automatically increase money.
- Impressions without clicks: review targeting and cover/title/price alignment before assuming the bid is wrong.
- Clicks without mature orders: check attribution age, listing/sample, intent and agreed test loss; sparse evidence is not a conclusive failure.
- Mature loss beyond the reviewed experiment limit: propose precise pause/negative/bid/listing changes supported by the right scope.
- Positive measured contribution: check returns, variance and audience overlap before a small authorized next experiment. Report association, not proven incrementality.

## Monitor as an actual loop

Ask/confirm cadence, timezone, alert preference, review-only versus reviewed pause-only scope and expiry. Register the existing durable monitor, attach a real host scheduler if available, save its real job ID and verify a first run. A configured worker or schedule description is not running monitoring. Remain quiet on unchanged nonactionable results; surface blockers, budget events and useful decisions. If credentials expire, reports fail or scope changes, report the failure and suspend dependent actions. No unsupervised budget escalation.

For KDP publication status, inspect real Bookshelf/public listing receipts through the available attended browser; do not invent a KDP status/upload API. For royalties/payments, use the actual available report/export route. A scheduler cannot inspect an expired attended login. Distinguish an ad report's attributed sales, KDP estimated royalties and paid bank receipts. Tell the author what is live, measured, changed, unknown and the one next decision. Feed learning back into the listing/book and the next original title without promising income.

Official sources checked 3 October 2026; refresh for the selected account:
[author Sponsored Products guide](https://advertising.amazon.com/library/guides/authors-guide-to-sponsored-products), [API access](https://advertising.amazon.com/about-api/), [budget guidance](https://advertising.amazon.com/en-ca/library/guides/sponsored-products-budget-best-practices). Generic/locale-specific advice is not an account contract; actual schema and settings control supported actions. See references 17, 20, 21 and 22 for existing execution/report/monitor contracts.
