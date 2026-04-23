# 任务状态存储模块
# 目前为内存存储，后续可扩展为文件/数据库持久化

from astrbot.api import logger


class TaskStore:
    """轻量任务状态存储"""

    def __init__(self):
        self._tasks = {}

    def create(self, task_id: str, data: dict) -> dict:
        task = {
            "task_id": task_id,
            "status": "pending",
            **data,
        }
        self._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> dict | None:
        return self._tasks.get(task_id)

    def update(self, task_id: str, **kwargs) -> dict | None:
        task = self._tasks.get(task_id)
        if task:
            task.update(kwargs)
        return task

    def list_by_user(self, user_id: str, limit: int = 10) -> list[dict]:
        return [
            t for t in self._tasks.values()
            if t.get("user_id") == user_id
        ][-limit:]

    def cleanup_old(self, max_age_minutes: int = 60):
        """清理过期任务记录"""
        import time
        now = time.time()
        cutoff = now - max_age_minutes * 60
        to_remove = [
            tid for tid, t in self._tasks.items()
            if t.get("created_at", 0) < cutoff
        ]
        for tid in to_remove:
            del self._tasks[tid]
        if to_remove:
            logger.debug(f"清理了 {len(to_remove)} 条过期任务记录")
