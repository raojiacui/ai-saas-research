# AI SaaS 调研

这个仓库用于记录 AI SaaS 方向的产品、真实收入、用户需求和外链机会调研

当前项目已经从纯人工探索进入 **Agent 批量寻找 + 人工校验合并** 阶段：Agent 负责放大搜索、整理和 CSV 初步归档，最终是否可用仍由人工抽查、筛选、去重后合并

## 数据源

- 产品发现：Toolify、Product Hunt、SaaSHub、AlternativeTo、AI 工具目录、竞品官网
- 流量与关键词：AITDK、Similarweb/Toolify/AIPURE 等第三方公开口径
- 真实收入：TrustMRR、公开 ARR/MRR 信息、创始人访谈、媒体报道
- 外链机会：Ahrefs Backlink Checker、AI Directory、SaaS Directory、Product Launch、Review、Listicle、Community
- 用户需求：Reddit、Hacker News、GitHub Issues / Discussions、Product Hunt 评论、垂直社区

## 数据文件

| 文件 | 当前行数 | 说明 |
|------|----------|------|
| `demands.csv` | 192 | 用户需求与问题场景 |
| `products.csv` | 93 | AI 视频相关产品和竞品 |
| `revenue-products.csv` | 60 | 已有收入或商业化迹象的产品 |
| `backlinks.csv` | 99 | 可参考或可复制的外链机会 |

## 当前状态

| 工作 | 状态 | 说明 |
|------|------|------|
| 发现 AI 产品 | Agent 寻找 + 人工校验中 | 已合并多批竞品数据，继续按产品名、官网和域名去重 |
| AITDK 流量分析 | Agent 整理 + 人工校验中 | 月访问量、Top Keywords、Top Regions 作为判断依据，第三方口径需抽查 |
| TrustMRR / 收入分析 | Agent 寻找 + 人工校验中 | 收入、MRR、ARR、近 30 天收入需要保留来源口径，不能只看金额 |
| Ahrefs / 外链整理 | Agent 寻找 + 人工校验中 | 优先保留可提交、可复制、高/中优先级外链机会 |
| 用户需求收集 | Agent 寻找 + 人工校验中 | 只保留具体用户、具体场景、具体问题，并保留原始 URL |
| 自动化脚本 | 尚未沉淀 | `scripts/` 当前只有占位文件，现阶段主要是 Agent 执行 + 人工验收 |

## 自动化运行方式

暂无稳定可复用脚本

当前运行方式是：

1. 先由人工明确字段标准和样例
2. 让 Agent 按同一口径批量寻找、整理为 CSV
3. 人工检查字段完整性、来源可信度、重复项和是否值得保留
4. 通过 CSV 解析和行列数检查后合并进主表
5. 流程稳定后，再把可复用步骤沉淀到 `scripts/`

## 填写规范

- [CSV 填写标准](CSV_FILLING_STANDARD.md)
- 每条记录必须保留来源 URL 或可追溯来源
- 不要把同一个产品、同一个提交渠道或同一个需求场景重复写入主表
- Agent 结果不能直接视为最终结论，必须经过人工校验

## 当前问题

- 第三方流量、关键词、MRR/ARR 口径不完全一致，需要继续人工抽查
- 一些外链机会只有提交入口或榜单页面，真实收录条件需要后续人工验证
- `scripts/` 还没有形成稳定自动化，暂时不能一键复跑
- 当前 CSV 已有多批 Agent 数据，后续新增时要继续严格去重和校验
