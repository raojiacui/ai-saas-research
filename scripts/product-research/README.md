# product-research MVP

This workflow writes all automation results to one file: `pending-products.csv`.
It never modifies the official `products.csv`.

## Scope

- Reads `products.csv` and `pending-products.csv` before each run for dedupe
- Dedupes by normalized product name and website domain
- Fetches each official homepage with explicit timeout and bounded retries
- Extracts deterministic fields from HTML
- Sends only trimmed webpage text to an optional LLM provider
- Applies domain admission before marking a row as `pending`
- Writes every non-duplicate result to `pending-products.csv` with `status`
- Writes a Markdown run report to `runs/`

## Status Values

- `pending`: accepted by the current focus filter; review before merging the first 11 columns into `products.csv`
- `skipped`: fetched and classified, but outside the current focus
- `failed`: fetch, validation, or model step failed

Duplicates are reported but not appended, to avoid repeatedly cluttering the table.

## Example

Auto-discover a tiny Toolify sample, dedupe against `products.csv` and `pending-products.csv`, then enrich each official homepage:

```powershell
python scripts/product-research/run.py `
  --discover-source toolify `
  --limit 5 `
  --llm-provider deepseek `
  --focus reference-to-video `
  --discover-timeout 15 `
  --fetch-timeout 15 `
  --llm-timeout 30 `
  --max-retries 1
```

When `--discover-query` is omitted, the workflow uses a built-in AI video query pool:

- `reference to video ai`
- `video to video ai`
- `image to video ai`
- `text to video ai`
- `ai video generator`
- `ai video editor`
- `ai video ads`
- `ai avatar video`
- `ai lip sync video`
- `motion transfer video ai`
- `video style transfer ai`
- `product to video ads ai`

To override the pool, repeat `--discover-query`:

```powershell
python scripts/product-research/run.py `
  --discover-source toolify `
  --discover-query "ai video ads" `
  --discover-query "image to video ai" `
  --discover-query "ai lip sync video" `
  --limit 5 `
  --llm-provider deepseek `
  --focus reference-to-video `
  --max-retries 1
```

Manual candidates still work:

```powershell
python scripts/product-research/run.py `
  --candidate "TopView AI|https://www.topview.ai/|https://www.topview.ai/|manual-test" `
  --llm-provider deepseek `
  --focus reference-to-video `
  --limit 1
```

Use `--llm-provider deepseek` when `DEEPSEEK_API_KEY` is set. The default DeepSeek model is `deepseek-v4-flash`. The workflow does not let the model browse; it sends only a trimmed homepage excerpt and requests fixed JSON fields.
