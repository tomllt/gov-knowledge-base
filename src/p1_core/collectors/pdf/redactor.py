"""敏感字段脱敏中间件。

针对中文政务文本中常见的隐私字段进行识别与替换,遵循 P1-F01 §业务规则:
    "敏感字段 (人员身份信息、联系方式等) 在接入时自动脱敏,
     不进入原始数据存储。"

支持的脱敏模式 (按优先级从高到低,长/特异优先):
    1. 居民身份证号  -> ``[REDACTED:id_card]``    (18 位,末位可为 X/x)
    2. 中国大陆手机号 -> ``[REDACTED:phone]``      (11 位,1 开头)
    3. 银行卡号       -> ``[REDACTED:bank_card]``  (16-19 位连续数字)

本模块为纯函数式中间件,不读写文件,不依赖任何运行时配置。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """脱敏结果。

    Attributes:
        text: 脱敏后的文本。
        hits: 命中敏感字段的总次数 (跨类型求和)。
        counts: 各类型命中次数,例如 ``{"id_card": 1, "phone": 2}``。
    """

    text: str
    hits: int
    counts: dict[str, int]


# 组合正则 (按优先级从高到低排列,长/特异在前):
#   id_card  18 位,末位可为数字或 X/x;必须在词边界
#   phone    11 位,首位 1;在词边界 (避免与银行卡 16+ 位冲突)
#   bank_card 16-19 位连续数字;在词边界
#   顺序关键: Python ``re`` 在 alternation 中首个匹配胜出,
#   因此更特异/更长的模式必须先出现,以避免被覆盖。
_REDACT_RE: re.Pattern[str] = re.compile(
    r"\b(?:\d{17}[\dXx]|1\d{10}|\d{16,19})\b",
)


def _classify(match: re.Match[str]) -> str:
    """根据匹配文本判定类型并返回替换串。"""
    text = match.group(0)
    length = len(text)
    # 优先级与正则 alternation 顺序保持一致 (长度优先):
    #   18 位   -> 身份证号 (末位可为数字或 X/x,两种都是合法格式)
    #   11 位 1 开头 -> 手机号
    #   16-19 位  -> 银行卡号 (兜底)
    if length == 18:
        return "[REDACTED:id_card]"
    if length == 11 and text.startswith("1"):
        return "[REDACTED:phone]"
    return "[REDACTED:bank_card]"


class SensitiveRedactor:
    """敏感字段脱敏器 (不可变、无副作用)。"""

    __slots__ = ()

    def redact(self, text: str) -> RedactionResult:
        """对 ``text`` 执行单遍脱敏,返回结果对象。

        算法:
            1. 优先使用 ID-正则/手机-正则/银行卡-正则单遍匹配;
            2. 对每个匹配根据形态判定类型并替换;
            3. 累计 ``hits`` 与 ``counts``。
        """
        if not text:
            return RedactionResult(text=text, hits=0, counts={})

        counts: Counter[str] = Counter()

        def _replace(match: re.Match[str]) -> str:
            tag = _classify(match)
            # 提取类型标签 "id_card" / "phone" / "bank_card"
            counts[tag.removeprefix("[REDACTED:").removesuffix("]")] += 1
            return tag

        redacted = _REDACT_RE.sub(_replace, text)
        return RedactionResult(
            text=redacted,
            hits=sum(counts.values()),
            counts=dict(counts),
        )


__all__ = ["RedactionResult", "SensitiveRedactor"]
