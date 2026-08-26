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

```powershell
python scripts/product-research/run.py `
  --candidate "TopView AI|https://www.topview.ai/|https://www.topview.ai/|manual-test" `
  --llm-provider deepseek `
  --focus reference-to-video `
  --limit 1
```

Use `--llm-provider deepseek` when `DEEPSEEK_API_KEY` is set. The default DeepSeek model is `deepseek-v4-flash`. The workflow does not let the model browse; it sends only a trimmed homepage excerpt and requests fixed JSON fields.
