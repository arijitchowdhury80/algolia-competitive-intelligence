# Dashboard Run Trace Design Thinking

## Mental model

The dashboard user is asking, "Can I trust this read?" They need a trace of what Hermes ran and what Argus prioritized, not an admin control surface.

## Information architecture

Hero: unchanged. The dashboard's primary job remains the market read.

Primary: a small run-trace proof strip in the trust/operations area.

Secondary: product-market chain status, prioritized target count, Scout artifact count, runner verdict.

Supporting: first prioritized company/surface/reason and learning instruction count.

## Interaction flow

1. User reads the market recommendation.
2. User checks the run trace to see whether the product-market muscle ran.
3. If coverage is degraded, the trace explains which surface Argus prioritized next.

Empty state: "No product-market run trace recorded." It must not look like success.

## Cognitive load

One bounded proof strip only. Do not add another table or another dashboard section.

## Emotional journey

Move from skepticism to grounded confidence: the recommendation is not just prose; it has an execution trace.

## Pre-mortem

Risk: the strip becomes technical noise.
Mitigation: only show status, counts, verdict, and first prioritized target.

Risk: the cockpit implies live Scout ran when it did not.
Mitigation: status comes from `product_market_summary.status`; missing data renders as not recorded.

