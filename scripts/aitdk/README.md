# AITDK Update

This folder handles the AITDK stage after product candidates already exist.

Browser agents read AITDK data. This script only writes verified metrics back to an existing CSV row.

## Fields Updated

- `AITDK月访问量`
- `Top Keywords`
- `Top Regions`

The default target is `pending-products.csv`. The script does not create new product rows.

## Input Format

Use one pipe-delimited row per product:

```text
产品名|官网域名|AITDK月访问量|Top Keywords|Top Regions
Runway|runwayml.com|12.3M|runway ai; ai video generator|United States; India; Brazil
```

CSV input also works when it has these columns:

- `产品名`
- `官网域名` or `网址` or `domain`
- `AITDK月访问量`
- `Top Keywords`
- `Top Regions`

## Commands

Dry run first:

```powershell
python scripts\aitdk\update.py --input-file .\aitdk-results.txt --dry-run
```

Write to `pending-products.csv`:

```powershell
python scripts\aitdk\update.py --input-file .\aitdk-results.txt
```

Overwrite existing AITDK fields only when you intentionally want to refresh old metrics:

```powershell
python scripts\aitdk\update.py --input-file .\aitdk-results.txt --overwrite
```

## Browser Agent Prompt

Paste this into Claude Code or OpenCode Go:

```text
你现在位于 D:\ai-saas-research。

任务：只补 AITDK 数据，不做产品发现，不修改 products.csv。

目标：
从 pending-products.csv 中选择 status=pending 且 AITDK月访问量 为空或 unavailable 的前 10 个产品，使用浏览器打开产品官网和 AITDK，读取：
- AITDK月访问量
- Top Keywords
- Top Regions

要求：
1. 使用 Playwright 浏览器操作。
2. 不手动修改 pending-products.csv。
3. 不修改 products.csv。
4. 每个产品最多尝试 2 次，每个页面等待不超过 30 秒。
5. 如果 AITDK 查不到数据，写 unavailable。
6. 输出到 aitdk-results.txt，每行格式必须是：
   产品名|官网域名|AITDK月访问量|Top Keywords|Top Regions
7. Top Keywords 和 Top Regions 多个值用英文分号加空格分隔。
8. 最多处理 10 个，完成后停止。
9. 写完 aitdk-results.txt 后，先运行：
   python scripts\aitdk\update.py --input-file .\aitdk-results.txt --dry-run
10. 如果 dry-run 没有 unmatched，再运行：
   python scripts\aitdk\update.py --input-file .\aitdk-results.txt
11. 最后汇报 updated / unmatched，以及哪些产品仍需要人工复核。
```
