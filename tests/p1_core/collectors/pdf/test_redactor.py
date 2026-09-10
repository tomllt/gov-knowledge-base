"""敏感字段脱敏中间件测试。

支持的脱敏模式:
    - 居民身份证号 (18 位,末位可为 X)
    - 中国大陆手机号 (11 位,1 开头)
    - 银行卡号 (16-19 位连续数字)

脱敏策略:替换为 ``[REDACTED:<type>]`` 标记,并累计命中计数。
"""

from __future__ import annotations

import pytest

from p1_core.collectors.pdf.redactor import (
    RedactionResult,
    SensitiveRedactor,
)


class TestSensitiveRedactor:
    """基础脱敏行为。"""

    def test_empty_text_returns_empty_result(self) -> None:
        redactor = SensitiveRedactor()
        result = redactor.redact("")
        assert result.text == ""
        assert result.hits == 0
        assert result.counts == {}

    def test_no_sensitive_text_unchanged(self) -> None:
        redactor = SensitiveRedactor()
        text = "本指南适用于上海市公安局办事大厅。"
        result = redactor.redact(text)
        assert result.text == text
        assert result.hits == 0

    def test_id_card_redacted(self) -> None:
        redactor = SensitiveRedactor()
        text = "申请人身份证号:31010119900307888X,请核对。"
        result = redactor.redact(text)
        assert "[REDACTED:id_card]" in result.text
        assert "31010119900307888X" not in result.text
        assert result.counts["id_card"] == 1
        assert result.hits == 1

    def test_phone_number_redacted(self) -> None:
        redactor = SensitiveRedactor()
        text = "联系电话:13812345678,办公时间 9:00-17:00。"
        result = redactor.redact(text)
        assert "[REDACTED:phone]" in result.text
        assert "13812345678" not in result.text
        assert result.counts["phone"] == 1

    def test_bank_card_redacted(self) -> None:
        redactor = SensitiveRedactor()
        text = "收款账户:6222021234567890123,请确认到账。"
        result = redactor.redact(text)
        assert "[REDACTED:bank_card]" in result.text
        assert "6222021234567890123" not in result.text
        assert result.counts["bank_card"] == 1

    def test_multiple_hits_aggregated(self) -> None:
        redactor = SensitiveRedactor()
        text = (
            "张三 31010119900307888X, "
            "李四 410101199203074321, "
            "联系电话 13812345678 / 13987654321, "
            "卡号 6222021234567890123 9558800012345678。"
        )
        result = redactor.redact(text)
        assert result.hits == 6
        assert result.counts == {
            "id_card": 2,
            "phone": 2,
            "bank_card": 2,
        }
        # 原文敏感数据全部消失
        assert "31010119900307888X" not in result.text
        assert "13812345678" not in result.text
        assert "6222021234567890123" not in result.text

    def test_phone_number_must_start_with_1(self) -> None:
        """非 1 开头的 11 位连续数字不应被识别为手机号。"""
        redactor = SensitiveRedactor()
        # 21812345678 不应被命中
        text = "工单号:21812345678 已处理。"
        result = redactor.redact(text)
        assert "21812345678" in result.text
        assert result.counts.get("phone", 0) == 0

    def test_short_bank_card_not_matched(self) -> None:
        """15 位及以下数字不命中银行卡号 (避免与身份证号/短编码混淆)。"""
        redactor = SensitiveRedactor()
        # 16 位以下应不命中
        text = "编号 12345678901234 结束。"
        result = redactor.redact(text)
        assert result.counts.get("bank_card", 0) == 0

    def test_redact_result_dataclass_immutable(self) -> None:
        result = RedactionResult(text="x", hits=0, counts={})
        with pytest.raises((AttributeError, Exception)):
            result.text = "y"  # type: ignore[misc]
