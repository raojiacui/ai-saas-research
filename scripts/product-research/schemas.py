"""Shared schemas for the product research MVP."""

PRODUCT_HEADERS = [
    "产品名",
    "网址",
    "给谁用",
    "输入",
    "输出",
    "价格",
    "解决什么问题",
    "为什么值得继续看",
    "AITDK月访问量",
    "Top Keywords",
    "Top Regions",
]

SEMANTIC_FIELDS = [
    "给谁用",
    "输入",
    "输出",
    "解决什么问题",
    "为什么值得继续看",
]

VIDEO_CATEGORY_FIELDS = [
    "ai_video_fit",
    "ai_video_evidence",
    "video_category",
    "reference_to_video_fit",
    "reference_to_video_evidence",
]

VIDEO_CATEGORIES = [
    "Reference-to-Video / 视频二创控制",
    "动作参考 / Motion Transfer",
    "风格参考 / Video Style Transfer",
    "人物或主体一致性 / Character or Subject Consistency",
    "视频广告克隆 / Video Ad Cloner",
    "产品图或URL转视频广告 / Product-to-Video Ads",
    "视频反推Prompt / Video-to-Prompt",
    "局部替换 / Object or Face Replacement",
    "唇形同步与配音本地化 / Lip Sync and Localization",
    "AI视频编辑 / AI Video Editing",
    "长视频转短视频 / Long-to-Short Video",
    "数字人 / Avatar Video",
    "文生视频 / Text-to-Video",
    "图生视频 / Image-to-Video",
    "视频理解 / Video Understanding",
    "多模型聚合器 / Multi-model Aggregator",
    "工作流或API管线 / Workflow or API Pipeline",
    "其他 / Other",
]

RESULT_HEADERS = [
    "status",
    "reason",
    "source_url",
    "candidate_url",
    "domain",
    "final_url",
    "http_status",
    "html_fetcher",
    "page_title",
    "meta_description",
    "pricing_url",
    "ai_video_fit",
    "ai_video_evidence",
    "video_category",
    "reference_to_video_fit",
    "reference_to_video_evidence",
    "llm_provider",
    "llm_model",
    "llm_calls",
    "failed_step",
    "error_code",
    "error",
    "retry_count",
    "timestamp",
]

PENDING_HEADERS = PRODUCT_HEADERS + RESULT_HEADERS

REPORT_HEADERS = [
    "started_at",
    "finished_at",
    "candidates",
    "created",
    "skipped",
    "duplicates",
    "failed",
    "llm_calls",
]
