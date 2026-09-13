"""GitHub issue policy that is independent from network and database access."""
from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

from ..config import settings


STATUS_LABEL_PREFIX = "status:"
STATUS_LABELS = {
    "submitted": ("status: submitted", "d4c5f9", "已提交，等待分析"),
    "triaging": ("status: triaging", "bfdadc", "正在分析"),
    "pending_review": ("status: pending-review", "fbca04", "等待人工审核"),
    "needs_information": ("status: needs-information", "fef2c0", "需要补充信息"),
    "candidate": ("status: candidate", "0e8a16", "版本开发候选"),
    "accepted": ("status: accepted", "0e8a16", "规格已批准"),
    "scheduled": ("status: scheduled", "1d76db", "已进入版本范围"),
    "developing": ("status: developing", "5319e7", "正在开发"),
    "testing": ("status: testing", "7057ff", "正在测试"),
    "release_ready": ("status: release-ready", "006b75", "等待发布"),
    "merged": ("status: merged", "8250df", "已合并，等待发布"),
    "released": ("status: released", "0e8a16", "已发布"),
    "deferred": ("status: deferred", "c5def5", "暂缓处理"),
    "rejected": ("status: rejected", "d73a4a", "未采纳"),
    "duplicate": ("status: duplicate", "cfd3d7", "重复需求"),
    "withdrawn": ("status: withdrawn", "cfd3d7", "提交者已撤回"),
    "closed": ("status: closed", "6a737d", "已关闭"),
}
GITHUB_CLOSED_REQUIREMENT_STATUSES = {"released", "rejected", "duplicate", "withdrawn", "closed"}
CLOSING_ISSUE_PATTERN = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+(?:[\w.-]+/[\w.-]+)?#(\d+)\b"
)


def closing_issue_numbers(pull_request: dict[str, Any]) -> set[int]:
    return {int(number) for number in CLOSING_ISSUE_PATTERN.findall(pull_request.get("body") or "")}


def pull_request_summary(pull_request: dict[str, Any]) -> dict[str, Any]:
    merged = bool(pull_request.get("merged") or pull_request.get("merged_at"))
    return {
        "number": pull_request.get("number"),
        "title": pull_request.get("title") or f"Pull Request #{pull_request.get('number')}",
        "url": pull_request.get("html_url"),
        "state": "merged" if merged else pull_request.get("state", "open"),
        "draft": bool(pull_request.get("draft")),
        "merged_at": pull_request.get("merged_at"),
        "updated_at": pull_request.get("updated_at"),
    }


def github_state_for_requirement(status: str) -> str:
    return "closed" if status in GITHUB_CLOSED_REQUIREMENT_STATUSES else "open"


def requirement_status_from_github(
    issue: dict[str, Any],
    current_status: str = "submitted",
    action: str | None = None,
    changed_label: str | None = None,
) -> str:
    status_by_label = {label.lower(): status for status, (label, _color, _description) in STATUS_LABELS.items()}
    labels = {
        (item.get("name", "") if isinstance(item, dict) else str(item)).lower()
        for item in issue.get("labels", [])
    }
    matched = {status_by_label[label] for label in labels if label in status_by_label}
    if matched == {current_status} and issue.get("state") == github_state_for_requirement(current_status):
        return current_status
    if action == "closed":
        return "closed"
    if action == "reopened":
        return "pending_review"
    if action == "labeled" and changed_label and changed_label.lower() in status_by_label:
        return status_by_label[changed_label.lower()]
    if len(matched) == 1:
        label_status = matched.pop()
        if issue.get("state") != github_state_for_requirement(label_status):
            return "closed" if issue.get("state") == "closed" else "pending_review"
        return label_status
    if issue.get("state") == "closed":
        return "closed"
    return current_status


def verify_webhook(body: bytes, signature: str | None) -> bool:
    if not settings.github_webhook_secret:
        return False
    expected = "sha256=" + hmac.new(settings.github_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    return bool(signature and hmac.compare_digest(expected, signature))
