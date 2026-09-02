from __future__ import annotations

import csv
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "revenue-products.csv"
REPORT_DIR = ROOT / "runs"
HEADERS = [
    "产品名",
    "网址",
    "做什么",
    "MRR",
    "近30天收入",
    "价格",
    "目标用户",
    "输入",
    "输出",
    "AITDK月访问量",
    "Top Keywords",
    "为什么有人愿意付钱",
]

EXACT_MONEY_RE = re.compile(r"^\$\d[\d,]*(?:\.\d+)?\s*/?\s*$")
TRUST_SUFFIX_RE = re.compile(r"\s*[（(]\s*TrustMRR公开记录\s*[）)]\s*$")
BAD_REVENUE_RE = re.compile(r"很高|较高|中等|较低|未知|ARR|年化|收入|融资|估算|披露|财报|公开|TrustMRR|用户|盈利")
PLACEHOLDER_PRICE_RE = re.compile(r"TrustMRR未披露价格|官网价格需二次复核|具体以官网为准|以官网为准|需二次复核|未披露价格|\b约\s*\$|约 \$|免费层 \+ 订阅|免费层 \+ 会员订阅|订阅制（约|应用内订阅（约|\(约")
WHY_REVENUE_RE = re.compile(r"TrustMRR公开收入|来源：https?://trustmrr\.com|MRR\s*\$|近30天\s*\$|累计\s*\$")
ENGLISH_SENTENCE_RE = re.compile(r"^[A-Za-z0-9 .,'/&+\-:()]+$")


def strip_trust_suffix(value: str) -> str:
    return TRUST_SUFFIX_RE.sub("", (value or "").strip()).strip()


def clean_money(value: str) -> tuple[str, bool]:
    original = value or ""
    stripped = strip_trust_suffix(original)
    changed = stripped != original.strip()
    if not stripped:
        return "", changed
    if EXACT_MONEY_RE.match(stripped):
        return stripped.rstrip(" /"), changed
    if BAD_REVENUE_RE.search(stripped):
        return "", True
    return stripped, changed


def is_english_only(value: str) -> bool:
    text = (value or "").strip()
    return bool(text and ENGLISH_SENTENCE_RE.match(text) and re.search(r"[A-Za-z]", text))


def clean_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    changes: list[dict] = []
    for idx, row in enumerate(rows, start=1):
        for header in HEADERS:
            row.setdefault(header, "")
            row[header] = re.sub(r"[\r\n\t]+", " ", row.get(header, "") or "").strip()

        before_mrr = row["MRR"]
        before_last = row["近30天收入"]
        row["MRR"], mrr_changed = clean_money(row["MRR"])
        row["近30天收入"], last_changed = clean_money(row["近30天收入"])
        if mrr_changed or row["MRR"] != before_mrr:
            changes.append({"行号": idx, "产品名": row["产品名"], "字段": "MRR", "原值": before_mrr, "新值": row["MRR"]})
        if last_changed or row["近30天收入"] != before_last:
            changes.append({"行号": idx, "产品名": row["产品名"], "字段": "近30天收入", "原值": before_last, "新值": row["近30天收入"]})

        before_price = row["价格"]
        if PLACEHOLDER_PRICE_RE.search(before_price or ""):
            row["价格"] = ""
            changes.append({"行号": idx, "产品名": row["产品名"], "字段": "价格", "原值": before_price, "新值": ""})

        before_do = row["做什么"]
        if is_english_only(before_do):
            row["做什么"] = ""
            changes.append({"行号": idx, "产品名": row["产品名"], "字段": "做什么", "原值": before_do, "新值": ""})

        before_why = row["为什么有人愿意付钱"]
        if WHY_REVENUE_RE.search(before_why or ""):
            row["为什么有人愿意付钱"] = ""
            changes.append({"行号": idx, "产品名": row["产品名"], "字段": "为什么有人愿意付钱", "原值": before_why, "新值": ""})
    return rows, changes


def audit(rows: list[dict]) -> dict:
    need_revenue = []
    need_profile = []
    ready = []
    for idx, row in enumerate(rows, start=1):
        missing_revenue = not row.get("MRR") or not row.get("近30天收入")
        missing_profile = any(not row.get(field) for field in ["做什么", "价格", "为什么有人愿意付钱"])
        if missing_revenue:
            need_revenue.append((idx, row.get("产品名", "")))
        if missing_profile:
            need_profile.append((idx, row.get("产品名", "")))
        if not missing_revenue and not missing_profile:
            ready.append((idx, row.get("产品名", "")))
    return {"total": len(rows), "ready": ready, "need_revenue": need_revenue, "need_profile": need_profile}


def write_csv(rows: list[dict]) -> None:
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS, extrasaction="ignore", quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    REPORT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = CSV_PATH.with_name(f"revenue-products.backup-{stamp}.csv")
    shutil.copy2(CSV_PATH, backup)

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    rows, changes = clean_rows(rows)
    write_csv(rows)
    result = audit(rows)

    report = REPORT_DIR / f"revenue-products-clean-audit-{stamp}.md"
    with report.open("w", encoding="utf-8", newline="\n") as f:
        f.write("# revenue-products clean audit\n\n")
        f.write(f"- backup: {backup}\n")
        f.write(f"- total rows: {result['total']}\n")
        f.write(f"- usable rows after cleanup: {len(result['ready'])}\n")
        f.write(f"- rows still needing TrustMRR MRR/近30天收入: {len(result['need_revenue'])}\n")
        f.write(f"- rows still needing 做什么/价格/为什么有人愿意付钱: {len(result['need_profile'])}\n")
        f.write(f"- cells cleaned: {len(changes)}\n\n")
        f.write("## rows needing TrustMRR revenue\n")
        for i, name in result["need_revenue"]:
            f.write(f"- {i}: {name}\n")
        f.write("\n## rows needing product/pricing/value fields\n")
        for i, name in result["need_profile"]:
            f.write(f"- {i}: {name}\n")
        f.write("\n## cleaned cells\n")
        for c in changes:
            old = c["原值"].replace("\n", " ")[:220]
            new = c["新值"].replace("\n", " ")[:220]
            f.write(f"- row {c['行号']} {c['产品名']} / {c['字段']}: {old!r} -> {new!r}\n")

    print(f"backup={backup}")
    print(f"report={report}")
    print(f"total={result['total']}")
    print(f"usable_rows_after_cleanup={len(result['ready'])}")
    print(f"rows_still_needing_revenue={len(result['need_revenue'])}")
    print(f"rows_still_needing_profile_fields={len(result['need_profile'])}")
    print(f"cells_cleaned={len(changes)}")


if __name__ == "__main__":
    main()

