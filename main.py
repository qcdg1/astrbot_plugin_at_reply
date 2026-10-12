import time
import random
from sys import maxsize
from typing import List, Dict, Tuple

import astrbot.api.message_components as Comp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger


@register(
    "astrbot_plugin_at_reply",
    "your_name",
    "被@时随机回复，不走 LLM。支持群白名单、冷却、关键词放行和喷子模式。",
    "1.0.4",
    "https://github.com/your_name/astrbot_plugin_at_reply",
)
class AtReplyPlugin(Star):
    """被@时随机回复，不走 LLM；支持白名单、冷却、关键词放行和喷子模式。"""

    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}

        # ---- 读取配置 ----
        self.reply_pool: List[str] = self.config.get("reply_pool", ["厉不厉害你机哥"])
        self.cooldown_seconds: int = self.config.get("cooldown_seconds", 0)
        self.whitelist_enabled: bool = self.config.get("whitelist_enabled", False)
        self.group_whitelist: List[str] = self.config.get("group_whitelist", [])
        self.keyword: str = self.config.get("keyword", "")
        self.troll_pool: List[str] = self.config.get("troll_pool", ["你是不是找骂", "再@我试试", "烦不烦"])
        self.troll_window: int = self.config.get("troll_window_seconds", 60)
        self.troll_threshold: int = self.config.get("troll_threshold", 5)
        self.troll_duration: int = self.config.get("troll_duration_seconds", 120)

        # ---- 运行时状态 ----
        self.cooldown_map: Dict[str, float] = {}
        # (group_id, user_id) -> [时间戳列表]，用于窗口内计数
        self.mention_history: Dict[Tuple[str, str], List[float]] = {}
        # (group_id, user_id) -> 喷子模式到期时间戳
        self.troll_active_until: Dict[Tuple[str, str], float] = {}

        logger.info(
            f"[AtReply] 加载完成 | 回复池{len(self.reply_pool)}条 | "
            f"冷却{self.cooldown_seconds}s | 白名单{'开启' if self.whitelist_enabled else '关闭'} | "
            f"关键词='{self.keyword}' | 喷子阈值{self.troll_threshold}次/{self.troll_window}s | "
            f"喷子持续{self.troll_duration}s"
        )

    # ------------------------------------------------------------------
    # 工具函数
    # ------------------------------------------------------------------
    def _is_bot_mentioned(self, event: AstrMessageEvent) -> bool:
        bot_id = str(event.get_self_id())
        for seg in event.get_messages():
            if isinstance(seg, Comp.At) and str(seg.qq) == bot_id:
                return True
        return False

    def _text_after_mention(self, event: AstrMessageEvent) -> str:
        bot_id = str(event.get_self_id())
        found_at = False
        for seg in event.get_messages():
            if found_at:
                if isinstance(seg, Comp.Plain):
                    return seg.text
                break
            if isinstance(seg, Comp.At) and str(seg.qq) == bot_id:
                found_at = True
        return ""

    def _in_cooldown(self, group_id: str) -> bool:
        if self.cooldown_seconds <= 0:
            return False
        last = self.cooldown_map.get(group_id, 0)
        return (time.time() - last) < self.cooldown_seconds

    def _update_cooldown(self, group_id: str):
        self.cooldown_map[group_id] = time.time()

    def _is_troll_active(self, group_id: str, user_id: str) -> bool:
        """该用户当前是否处于喷子持续期内。"""
        key = (group_id, user_id)
        until = self.troll_active_until.get(key, 0)
        if until <= 0:
            return False
        if time.time() < until:
            return True
        # 已过期，清掉
        self.troll_active_until.pop(key, None)
        return False

    def _activate_troll(self, group_id: str, user_id: str):
        """进入喷子持续期，并清空历史计数。"""
        key = (group_id, user_id)
        if self.troll_duration > 0:
            self.troll_active_until[key] = time.time() + self.troll_duration
        self.mention_history.pop(key, None)

    def _record_mention(self, group_id: str, user_id: str) -> int:
        key = (group_id, user_id)
        now = time.time()
        history = self.mention_history.get(key, [])
        cutoff = now - self.troll_window
        history = [t for t in history if t > cutoff]
        history.append(now)
        self.mention_history[key] = history
        return len(history)

    # ------------------------------------------------------------------
    # 消息事件处理
    # ------------------------------------------------------------------
    @filter.event_message_type(filter.EventMessageType.ALL, priority=maxsize)
    async def on_group_message(self, event: AstrMessageEvent):
        if not self._is_bot_mentioned(event):
            return

        logger.info("[AtReply] 检测到@机器人")

        group_id = str(event.get_group_id())
        user_id = str(event.get_sender_id())

        # 白名单
        if self.whitelist_enabled and group_id not in self.group_whitelist:
            logger.debug(f"[AtReply] 群 {group_id} 不在白名单，放行给 LLM")
            return

        # 群冷却
        if self._in_cooldown(group_id):
            logger.debug(f"[AtReply] 群 {group_id} 冷却中，忽略 @")
            return

        # 关键词放行
        if self.keyword:
            after_text = self._text_after_mention(event)
            if after_text.startswith(self.keyword):
                logger.info(f"[AtReply] 命中关键词 '{self.keyword}'，放行给 LLM")
                return

        # 1) 已在喷子持续期内 → 直接喷
        if self._is_troll_active(group_id, user_id):
            reply = random.choice(self.troll_pool)
            logger.info(f"[AtReply] 喷子持续期内 | 群{group_id} 用户{user_id} → {reply}")
            yield event.plain_result(reply)
            event.should_call_llm(False)
            event.stop_event()
            return

        # 2) 未在持续期，正常计数判断是否触发
        mention_count = self._record_mention(group_id, user_id)
        if mention_count >= self.troll_threshold:
            reply = random.choice(self.troll_pool)
            logger.info(
                f"[AtReply] 喷子触发 | 群{group_id} 用户{user_id} "
                f"{self.troll_window}s 内 @ {mention_count} 次 | 进入 {self.troll_duration}s 持续期"
            )
            self._activate_troll(group_id, user_id)
            yield event.plain_result(reply)
            event.should_call_llm(False)
            event.stop_event()
            return

        # 3) 普通随机回复
        if not self.reply_pool:
            logger.warning("[AtReply] 回复池为空，不回复")
            return

        reply = random.choice(self.reply_pool)
        logger.info(f"[AtReply] 随机回复群 {group_id}: {reply}")
        yield event.plain_result(reply)
        event.should_call_llm(False)
        event.stop_event()
        self._update_cooldown(group_id)
        logger.info("[AtReply] 回复已发送，LLM 已禁止，冷却已更新")

    async def terminate(self):
        logger.info("[AtReply] 插件已卸载")