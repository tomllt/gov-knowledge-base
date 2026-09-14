"""P1 核心库结构化异常体系测试。"""

from __future__ import annotations

import pytest

from p1_core.exceptions import (
    ChunkError,
    IngestError,
    P1CoreError,
    ParseError,
    SerializationError,
    ValidationError,
)


class TestP1CoreErrorHierarchy:
    """验证异常继承结构稳定。"""

    def test_p1_core_error_is_exception(self) -> None:
        assert issubclass(P1CoreError, Exception)

    @pytest.mark.parametrize(
        "cls",
        [ValidationError, SerializationError, IngestError, ParseError, ChunkError],
    )
    def test_domain_errors_inherit_p1_core_error(self, cls: type[P1CoreError]) -> None:
        assert issubclass(cls, P1CoreError)

    def test_domain_errors_can_be_caught_by_base(self) -> None:
        try:
            raise ValidationError("boom")
        except P1CoreError as exc:
            assert isinstance(exc, ValidationError)


class TestExceptionMessages:
    """验证异常消息可读、跨子包可定位。"""

    def test_validation_error_message_preserved(self) -> None:
        err = ValidationError("field x is invalid")
        assert "field x is invalid" in str(err)
        assert isinstance(err, P1CoreError)
