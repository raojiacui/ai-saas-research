# product-research workflow

```text
explicit tiny candidate input
  -> read official products.csv and pending-products.csv
  -> build product-name and domain dedupe index
  -> report duplicates without appending them
  -> fetch homepage with timeout and max retry
  -> extract title, meta description, pricing URL, trimmed text
  -> optional LLM semantic classification with fixed JSON schema
  -> apply focus filter: reference-to-video by default
  -> append one result row to pending-products.csv with status=pending/skipped/failed
  -> write run report
```

## Data Protection

`products.csv` is read-only during product research runs. Human review is required before any pending row becomes official data.

## Single Table Output

`pending-products.csv` is the only automation result table. Its first 11 columns match `products.csv`; later columns are review metadata such as `status`, `reason`, source URL, domain, category, model calls, and errors.

## Failure Policy

No step retries forever. Homepage fetch defaults to one retry. LLM calls are at most one call per product. If the LLM is unavailable, the row will usually be skipped by the default focus filter instead of polluting pending review.
