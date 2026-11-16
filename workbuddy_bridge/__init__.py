from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from plugin.sdk.plugin import (
    Err,
    NekoPluginBase,
    Ok,
    SdkError,
    lifecycle,
    llm_tool,
    neko_plugin,
    plugin_entry,
)

CN_TZ = timezone(timedelta(hours=8))

# 队列默认放在插件自己所在目录下的 queue/ 子目录：
#   - 跟着插件走，不依赖任何"对话工作区"路径（清理历史对话不会误伤）
#   - 别人拿到插件也不用改配置就能跑
# 可用环境变量 WORKBUDDY_BRIDGE_ROOT 或 plugin.toml 的 [bridge] root 覆盖。
PLUGIN_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = str(PLUGIN_DIR / "queue")
ENV_OVERRIDE = "WORKBUDDY_BRIDGE_ROOT"


@neko_plugin
class WorkbuddyBridgePlugin(NekoPluginBase):
    """让猫娘把需要动手的活委派给 WorkBuddy，并把成果送回来。

    通道：本地文件队列（默认位于本插件目录下的 queue/）。
      queue/inbox/      猫娘写入待办任务 (*.json)
      queue/outbox/     WorkBuddy 写回成果 (*.json)
      queue/processed/  已处理任务与已读成果归档
      queue/artifacts/  产出文件（大文件放这里）
    """

    def __init__(self, ctx: Any):
        super().__init__(ctx)
        self.logger = ctx.logger
        self.root: Path = Path(os.environ.get(ENV_OVERRIDE) or DEFAULT_ROOT)
        self.channel: str = "file"
        self._inbox: Path | None = None
        self._outbox: Path | None = None
        self._processed: Path | None = None

    # ---------- helpers ----------

    def _now(self) -> str:
        return datetime.now(CN_TZ).isoformat(timespec="seconds")

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)

    def _ensure_dirs(self) -> None:
        # 兜底：即使 startup 生命周期未执行，也从 root 自行推导路径，
        # 避免手动入口/LLM 工具在 self._inbox is None 时 assert 失败。
        if self._inbox is None:
            self._inbox = self.root / "inbox"
        if self._outbox is None:
            self._outbox = self.root / "outbox"
        if self._processed is None:
            self._processed = self.root / "processed"
        for directory in (self._inbox, self._outbox, self._processed, self.root / "artifacts"):
            directory.mkdir(parents=True, exist_ok=True)

    # ---------- lifecycle ----------

    @lifecycle(id="startup")
    async def startup(self, **_):
        cfg = await self.config.dump()
        bridge = cfg.get("bridge", {}) or {}
        # 优先级：环境变量 > plugin.toml 的 [bridge] root > 插件目录下 queue/
        raw_root = (
            os.environ.get(ENV_OVERRIDE)
            or bridge.get("root")
            or DEFAULT_ROOT
        )
        self.channel = str(bridge.get("channel", "file"))
        self.root = Path(os.path.expandvars(str(raw_root)))
        self._inbox = self.root / "inbox"
        self._outbox = self.root / "outbox"
        self._processed = self.root / "processed"
        self._ensure_dirs()
        self.logger.info(
            "WorkBuddy bridge ready: root=%s channel=%s", self.root, self.channel
        )
        return Ok({"status": "ready", "root": str(self.root), "channel": self.channel})

    @lifecycle(id="shutdown")
    async def shutdown(self, **_):
        return Ok({"status": "stopped"})

    # ---------- conversation-time LLM tools ----------

    @llm_tool(
        name="delegate_to_workbuddy",
        description=(
            "把需要真正动手的任务委派给 WorkBuddy——一个能操作本地文件、查资料、"
            "生成 Word/Excel/PPT、写代码、分析数据的 AI 工作台。当用户要你帮忙完成"
            "具体工作而不只是陪聊时调用它（例如：搜索整理资料、做文档表格、写代码、"
            "跑数据分析、处理文件、生成PPT）。任务会进入队列，WorkBuddy 自动领取执行"
            "并把成果送回；完成后可用 check_workbuddy_results 查看。不要用它可以闲聊或回答简单问题。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "要 WorkBuddy 完成的任务，写清目标、要求和产出形式。",
                },
                "priority": {
                    "type": "string",
                    "description": "优先级：low / normal / high，默认 normal。",
                    "enum": ["low", "normal", "high"],
                },
            },
            "required": ["task"],
        },
        timeout=30.0,
    )
    async def delegate_to_workbuddy(self, *, task: str, priority: str = "normal"):
        task = (task or "").strip()
        if not task:
            return {
                "output": {"ok": False, "error": "任务内容不能为空"},
                "is_error": True,
                "error": "EMPTY_TASK",
            }
        if self._inbox is None:
            self._ensure_dirs()

        task_id = "tsk_" + datetime.now(CN_TZ).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        payload = {
            "version": 1,
            "task_id": task_id,
            "created_at": self._now(),
            "task": task,
            "priority": priority or "normal",
            "requester": "neko",
            "status": "pending",
        }
        target = self._inbox / f"{task_id}.json"
        try:
            await asyncio.to_thread(self._atomic_write_json, target, payload)
        except Exception as exc:  # noqa: BLE001
            return {
                "output": {"ok": False, "error": str(exc)},
                "is_error": True,
                "error": "WRITE_FAILED",
            }

        return {
            "output": {
                "ok": True,
                "task_id": task_id,
                "message": (
                    f"已经把任务交给 WorkBuddy 啦（编号 {task_id}），它会自动领走去办，"
                    "办好后成果会送回来。你可以用自己猫娘的口吻把这句转述给主人。"
                ),
            },
            "is_error": False,
        }

    @llm_tool(
        name="check_workbuddy_results",
        description=(
            "查看 WorkBuddy 已经完成的委派任务成果。当主人问起之前交给 WorkBuddy 的任务"
            "做好了没有、或你想汇报进度时调用它。返回成果摘要和产出文件路径；读走后成果会从队列移除。"
        ),
        parameters={"type": "object", "properties": {}},
        timeout=30.0,
    )
    async def check_workbuddy_results(self):
        if self._outbox is None:
            self._ensure_dirs()

        results: list[dict] = []
        for path in sorted(self._outbox.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            results.append(data)
            archive = self._processed / "results"
            archive.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(path, archive / path.name)
            except Exception as exc:  # noqa: BLE001
                # 归档失败不阻断读取，但要留痕：否则同一份成果可能被读两次
                self.logger.info(
                    "archive result failed (kept in outbox): %s -> %s (%s)",
                    path, archive, exc,
                )

        if not results:
            return {
                "output": {"ok": True, "count": 0, "message": "WorkBuddy 还没有送回新的成果。"},
                "is_error": False,
            }
        return {"output": {"ok": True, "count": len(results), "results": results}, "is_error": False}

    # ---------- manual entries (for testing in Plugin Manager) ----------

    @plugin_entry(
        id="delegate",
        name="委派任务给 WorkBuddy",
        description="手动测试：把一个任务写入桥接队列",
    )
    async def delegate_entry(self, task: str, priority: str = "normal", **_):
        result = await self.delegate_to_workbuddy(task=task, priority=priority)
        return Ok(result.get("output", result))

    @plugin_entry(
        id="fetch_results",
        name="收取 WorkBuddy 成果",
        description="手动测试：读取已完成的成果",
    )
    async def fetch_results_entry(self, **_):
        result = await self.check_workbuddy_results()
        return Ok(result.get("output", result))

    @plugin_entry(id="bridge_status", name="桥接状态", description="查看队列根目录与待办数量")
    async def bridge_status(self, **_):
        # 不依赖 startup 是否执行过：路径缺失时自行推导并建目录，
        # 否则首次加载会误报 pending=0、ready=0。
        if self._inbox is None or self._outbox is None:
            self._ensure_dirs()
        pending = len(list(self._inbox.glob("*.json")))
        ready = len(list(self._outbox.glob("*.json")))
        return Ok(
            {
                "root": str(self.root),
                "channel": self.channel,
                "pending": pending,
                "ready_results": ready,
            }
        )
