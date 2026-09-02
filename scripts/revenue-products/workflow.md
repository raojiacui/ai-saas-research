# revenue-products 自动补全流程

先运行清洗与审计：

```powershell
python scripts/revenue-products/clean_and_audit.py
```

当前口径：

- `做什么`：中文描述产品提供什么服务，不写收入。
- `MRR`：只填 TrustMRR 上的精确美元数，例如 `$12,106.00`，不写“较高/未知/ARR/来源”。
- `近30天收入`：同样只填 TrustMRR 上的精确美元数。
- `价格`：从产品官网 landing page 的 Pricing/Plans/Billing 页面提取明确套餐金额；找不到就留空，不能写“约”“以官网为准”。
- `为什么有人愿意付钱`：中文描述产品特别之处、好用之处、节省的成本或带来的结果，不写 MRR、近 30 天收入或来源。

批量补全建议先小批量跑：

```powershell
python scripts/revenue-products/research_fill.py --start 7 --limit 5 --llm claude
```

如果有 `DEEPSEEK_API_KEY`，也可以跑：

```powershell
python scripts/revenue-products/research_fill.py --start 7 --limit 5 --llm deepseek
```

确认 CSV 质量：

```powershell
python scripts/revenue-products/clean_and_audit.py
```

跑完整表时建议分批，避免网页限流和 LLM 一次性成本过高：

```powershell
python scripts/revenue-products/research_fill.py --start 7 --limit 25 --llm claude
python scripts/revenue-products/research_fill.py --start 32 --limit 25 --llm claude
python scripts/revenue-products/research_fill.py --start 57 --limit 25 --llm claude
```

Claude Code 执行要求：

1. 严格参考 `revenue-products.csv` 前 6 条的字段口径。
2. 对 TrustMRR 没有精确 MRR 或近 30 天收入的产品，收入字段留空，不要用 ARR、融资、估算或“高/中/低”。
3. 官网 pricing 页面打不开或没有明确套餐金额时，价格留空。
4. LLM 只负责把抓到的官网文本归纳成中文字段，不允许自己猜收入和价格。
5. 每批结束后查看 `runs/revenue-products-fill-*.md` 和 `runs/revenue-products-clean-audit-*.md`，继续从缺口最多的位置补。
