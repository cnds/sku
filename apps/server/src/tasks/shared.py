from __future__ import annotations

from celery import Task


def is_final_attempt(task: Task) -> bool:
    retries = int(getattr(task.request, "retries", 0))
    max_retries = int(getattr(task, "max_retries", 0) or 0)
    return retries >= max_retries


def retry_countdown(task: Task) -> int:
    retries = int(getattr(task.request, "retries", 0))
    return min(2**retries, 60)
