"""对话记忆持久化。

每轮问答结束后，把「用户问题 + 最终答复摘要」追加到 memory/AGENTS.md。
该文件会被 deepagents 的 MemoryMiddleware 在下一轮开始时注入系统提示，
因此这里的写入就是跨轮次的长期记忆。

约束：
- 记忆文件总大小硬上限 100 KB（UTF-8 字节数）。
- 超出上限时优先淘汰最旧的对话记录，最近一轮永远保留。
- 「长期偏好与规则」区留给 Agent 自己用 edit_file 维护，系统不会覆盖。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEMORY_PATH = PROJECT_ROOT / "memory" / "AGENTS.md"

# 记忆空间上限：100 KB
MAX_MEMORY_BYTES = 100 * 1024

# 单轮记录的截断长度，避免单条记录占满整个记忆空间
MAX_QUERY_CHARS = 300
MAX_ANSWER_CHARS = 1200

# 用于标记「系统维护的对话记忆区」，HTML 注释会在注入系统提示前被剔除
LOG_BEGIN = "<!-- memory-log:begin -->"
LOG_END = "<!-- memory-log:end -->"
TURN_BEGIN = "<!-- memory-turn:begin -->"
TURN_END = "<!-- memory-turn:end -->"

_ENTRY_RE = re.compile(
    re.escape(TURN_BEGIN) + r".*?" + re.escape(TURN_END),
    re.DOTALL,
)

_MEMORY_TEMPLATE = """# 用户记忆

> 发现长期偏好时，用 edit_file 写入「基本信息」或「出行偏好」；不要改写系统维护的「对话记忆」区。

本文件是 DeepAgent 的长期记忆，每轮对话开始时自动注入系统提示。
记忆文件总大小上限 **100 KB**，超出后最早的对话记录会被自动淘汰。

## 基本信息

（暂无）

## 出行偏好

（暂无）

## 历史规划记录

（暂无）

## 对话记忆（系统自动维护）

本区由程序在每轮对话结束后自动追加，请勿手工改写或删除。

{log_begin}
{log_end}
"""

# 使用线程锁串行化「读取-修改-写回」，避免并发请求互相覆盖记忆文件；
# 文件 I/O 在线程池中执行，锁不会阻塞事件循环。
_write_lock = threading.Lock()


def _empty_memory() -> str:
    """返回一份空的记忆文件内容。"""
    return _MEMORY_TEMPLATE.format(log_begin=LOG_BEGIN, log_end=LOG_END)


def _to_text(value: Any) -> str:
    """把模型返回的 content（字符串或 content blocks）转成纯文本。"""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for block in value:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return "" if value is None else str(value)


def _clean(text: str, limit: int) -> str:
    """折叠空白、转义会破坏记忆文件结构的标记，并按字符数截断。"""
    text = re.sub(r"\s+", " ", text).strip()

    # 避免用户内容里的 HTML 注释/闭合标签破坏记忆文件或系统提示结构
    text = (
        text.replace("<!--", "&lt;!--")
        .replace("-->", "--&gt;")
        .replace("</agent_memory>", "&lt;/agent_memory&gt;")
    )

    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def _format_entry(query: str, answer: str) -> str:
    """生成一轮对话的记忆记录。"""
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"{TURN_BEGIN}\n"
        f"### {timestamp}\n"
        f"- 用户：{query or '（空）'}\n"
        f"- Agent：{answer or '（本轮没有产生最终答复）'}\n"
        f"{TURN_END}"
    )


def _load_content() -> str:
    """读取记忆文件；不存在时返回初始模板。"""
    try:
        return MEMORY_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _empty_memory()


def _split(content: str) -> tuple[str, list[str], str]:
    """把记忆文件拆成：记忆区之前的内容、对话记录列表、记忆区之后的内容。"""
    begin = content.find(LOG_BEGIN)
    end = content.find(LOG_END, begin + len(LOG_BEGIN)) if begin != -1 else -1

    if begin == -1 or end == -1:
        # 标记被破坏（例如被手工删除）：把现有内容全部视作前置内容，
        # 并在末尾补一个新的对话记忆区，避免丢失已有偏好。
        head = content.rstrip()
        if "## 对话记忆" not in head:
            head += "\n\n## 对话记忆"
        return head, [], ""

    head = content[:begin].rstrip()
    body = content[begin + len(LOG_BEGIN):end]
    tail = content[end + len(LOG_END):].strip()

    entries = [match.group(0).strip() for match in _ENTRY_RE.finditer(body)]
    return head, entries, tail


def _compose(head: str, entries: list[str], tail: str = "") -> str:
    """按固定结构重新拼装记忆文件。"""
    parts = [head.rstrip(), LOG_BEGIN]
    if entries:
        parts.append("\n\n".join(entries))
    parts.append(LOG_END)
    if tail.strip():
        parts.append(tail.strip())
    return "\n\n".join(parts) + "\n"


def _byte_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _append_turn_sync(query: str, answer: str) -> None:
    """同步执行：加锁后追加记录并按 100 KB 上限裁剪。"""
    with _write_lock:
        _append_turn_locked(query, answer)


def _append_turn_locked(query: str, answer: str) -> None:
    """在持有写锁的前提下完成一次「读取-追加-裁剪-写回」。"""
    head, entries, tail = _split(_load_content())
    entries.append(_format_entry(query, answer))

    content = _compose(head, entries, tail)

    # 超出上限时从最旧的记录开始淘汰，至少保留最新一轮
    while _byte_len(content) > MAX_MEMORY_BYTES and len(entries) > 1:
        entries.pop(0)
        content = _compose(head, entries, tail)

    if _byte_len(content) > MAX_MEMORY_BYTES:
        # 极端情况：前置内容本身过大，或单条记录就超限。
        # 重置为最小结构，只保留最新一轮，保证硬上限。
        minimal_head = (
            "# DeepAgent 长期记忆\n\n"
            "本文件由系统自动维护，容量上限 100 KB。\n\n"
            "## 对话记忆"
        )
        safe_entry = _format_entry(_clean(query, 120), _clean(answer, 200))
        content = _compose(minimal_head, [safe_entry])
        logger.warning(
            "记忆文件超出 %d 字节，已重置为最小结构并保留最新一轮。",
            MAX_MEMORY_BYTES,
        )

    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 先写临时文件再原子替换，避免写入中断留下半截文件
    tmp_path = MEMORY_PATH.with_name(MEMORY_PATH.name + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, MEMORY_PATH)

    logger.debug(
        "已写入本轮记忆，共 %d 条记录，当前大小 %d 字节。",
        len(entries),
        _byte_len(content),
    )


async def remember_turn(query: str, answer: Any) -> None:
    """在一轮问答结束后持久化记忆。

    写入失败不应影响已经生成的回复，调用方需要自行捕获异常。
    """
    query_text = _clean(query, MAX_QUERY_CHARS)
    answer_text = _clean(_to_text(answer), MAX_ANSWER_CHARS)

    # 文件 I/O 放到线程池，避免阻塞事件循环；线程锁在 _append_turn_sync 内获取
    await asyncio.to_thread(_append_turn_sync, query_text, answer_text)


def memory_size_bytes() -> int:
    """返回当前记忆文件大小（字节），文件不存在时返回 0。"""
    try:
        return MEMORY_PATH.stat().st_size
    except FileNotFoundError:
        return 0
