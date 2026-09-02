# AI SaaS 调研

这个仓库用于记录 AI SaaS 方向的产品、真实收入、用户需求和外链机会调研

当前项目已经进入 **人工判断口径 + Agent 辅助整理 + 严格 CSV 校验** 阶段：核心判断仍以人工审核为准，Agent 只负责放大搜索、整理候选、格式化和复核，不能把低质量候选直接并入主表

## 数据源

- 产品发现：Toolify、Product Hunt、SaaSHub、AlternativeTo、AI 工具目录、竞品官网
- 流量与关键词：AITDK、Similarweb/Toolify/AIPURE 等第三方公开口径
- 真实收入：TrustMRR、公开 ARR/MRR 信息、创始人访谈、媒体报道
- 外链机会：Ahrefs Backlink Checker、AI Directory、SaaS Directory、Product Launch、Review、Listicle、Community
- 用户需求：Reddit、Hacker News、GitHub Issues / Discussions、Product Hunt 评论、垂直社区

## 数据文件

| 文件 | 当前行数 | 说明 |
|------|----------|------|
| `demands.csv` | 200 | 用户需求与问题场景；已剔除一批低含金量抱怨型记录，并补入更具体的 AI video 产品需求 |
| `products.csv` | 194 | AI 视频相关产品和竞品；已清理空/标记行，新增条目的 AITDK 字段已用可查公开口径补强或标记未收录 |
| `revenue-products.csv` | 161 | 已有收入或商业化迹象的产品；MRR/近 30 天收入按 TrustMRR 精确值口径整理，AITDK 月访问量与 Top Keywords 已完成一轮清理 |
| `backlinks.csv` | 200 | 可参考或可复制的外链机会；已按页面/域名去重并补齐复制判断 |

## 当前状态

| 工作 | 状态 | 说明 |
|------|------|------|
| 发现 AI 产品 | 当前本地 194 条，继续维护 | 已合并多批竞品数据，后续新增继续按产品名、官网和网址去重 |
| AITDK 流量分析 | 已完成一轮清理，继续抽查 | `products.csv` 与 `revenue-products.csv` 的 AITDK 月访问量和 Top Keywords 已清掉空白、unavailable、未核验；第三方无覆盖的小站统一标记为“未收录” |
| TrustMRR / 收入分析 | 当前本地 161 条，继续抽查 | MRR 和近 30 天收入保留 TrustMRR 精确美元数值口径；价格按官网 Pricing/Plans 明确套餐整理，缺少公开价格的继续留空 |
| Ahrefs / 外链整理 | 已补齐 200 条，继续验证收录条件 | 优先保留可提交、可复制、高/中优先级外链机会；无公开提交入口时写明不适用或需人工联系 |
| 用户需求收集 | 已补齐 200 条，已做质量筛选 | 已清掉空行/标记行、低价值抱怨型记录和重复原始 URL；只保留具体用户、具体场景、具体问题，并保留原始 URL |
| 自动化脚本 | 已有产品发现/AITDK/收入补全脚本，继续完善 | `scripts/product-research/` 负责发现、抓取、分类、去重并写入 `pending-products.csv`；`scripts/aitdk/` 负责 AITDK 指标回填与公开流量兜底；`scripts/revenue-products/` 负责收入表清洗、审计和补全 |

## 自动化运行方式

已有两类可复用脚本，但定位是“候选生成/指标回填”，不是直接替代人工判断。

- `scripts/product-research/`：产品发现 MVP。读取 `products.csv` 和 `pending-products.csv` 做去重，抓取官网，提取信息，可调用低成本模型分类，结果只写入 `pending-products.csv`，不直接修改 `products.csv`。
- `scripts/aitdk/`：AITDK 指标回填脚本。浏览器/人工读取 AITDK 后，把月访问量、Top Keywords、Top Regions 写回候选表；也包含 `fill_revenue_aitdk_fields.py`，用于对主表中空白、unavailable、未核验的 AITDK 字段做保守补齐。

当前运行方式是：

1. 先由人工明确字段标准和样例
2. 让 Agent 按同一口径批量寻找、整理为 CSV
3. 人工检查字段完整性、来源可信度、重复项和是否值得保留
4. 通过 CSV 解析和行列数检查后合并进主表
5. 流程稳定后，再继续把 demand、revenue、backlink 的可复用步骤沉淀到 `scripts/`

## 填写规范

- [CSV 填写标准](CSV_FILLING_STANDARD.md)
- 每条记录必须保留来源 URL 或可追溯来源
- 不要把同一个产品、同一个提交渠道或同一个需求场景重复写入主表
- Agent 结果不能直接视为最终结论，必须经过人工校验

## 当前问题

- 第三方流量、关键词、MRR/ARR 口径不完全一致，需要继续人工抽查
- 一些外链机会只有提交入口或榜单页面，真实收录条件需要后续人工验证
- `scripts/product-research/`、`scripts/aitdk/`、`scripts/revenue-products/` 已可用于候选生成、指标回填、收入表清洗和批量补全；`demands.csv`、`backlinks.csv` 还没有同等级别的稳定脚本
- 主表已经按更保守的 CSV 规则重写：全字段加引号、清理隐藏换行/控制字符、行列数校验通过
- 当前 CSV 已有多批 Agent 数据，后续新增时要继续严格去重、审核需求含金量，并避免把泛泛抱怨当作产品需求

## 最近更新

- 2026-08-29：四张主表 `products.csv`、`demands.csv`、`backlinks.csv`、`revenue-products.csv` 均补齐到 200 条；`backlinks.csv` 和 `revenue-products.csv` 已按全字段强转义重写，`demands.csv` 已替换一批低含金量需求。
- 2026-08-30：继续补 `products.csv` AITDK/公开流量口径，月访问量列已从“未知/未核验”改为可核验数值或明确无独立流量口径说明；`demands.csv` 替换 59 条重复 URL 记录，原始 URL 去重为 0；`revenue-products.csv` 同步 14 条与产品表匹配的流量/关键词口径。
- 2026-09-02：按当前本地文件状态更新：`products.csv` 为 194 条，已清理新增条目的 AITDK 字段；`revenue-products.csv` 为 161 条，已修正字段口径，并按 TrustMRR/官网价格/AITDK 或公开流量口径完成一轮补全，剩余无公开覆盖项标记为“未收录”。
