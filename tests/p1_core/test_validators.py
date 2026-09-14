"""模型校验工具测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from p1_core.exceptions import ValidationError
from p1_core.models._validators import (
    require_aware_datetime,
    require_line_range,
    require_nonempty_str,
    require_positive_page,
    require_str_dict,
)


class TestRequireNonemptyStr:
    """`require_nonempty_str` 边界条件。"""

    def test_valid_str(self) -> None:
        assert require_nonempty_str("hello", field="x") == "hello"

    def test_non_string_raises(self) -> None:
        with pytest.raises(ValidationError, match="must be str"):
            require_nonempty_str(42, field="x")  # type: ignore[arg-type]

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValidationError, match="must be non-empty"):
            require_nonempty_str("", field="x")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValidationError, match="must be non-empty"):
            require_nonempty_str("   ", field="x")

    def test_strips_whitespace_in_return(self) -> None:
        assert require_nonempty_str("  hi  ", field="x") == "hi"


class TestRequireAwareDatetime:
    """`require_aware_datetime` 边界条件。"""

    def test_aware_datetime_passes(self) -> None:
        dt = datetime(2026, 1, 1, tzinfo=UTC)
        assert require_aware_datetime(dt, field="t") is dt

    def test_naive_datetime_raises(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            require_aware_datetime(datetime(2026, 1, 1), field="t")

    def test_non_datetime_raises(self) -> None:
        with pytest.raises(ValidationError, match="must be datetime"):
            require_aware_datetime("not a dt", field="t")  # type: ignore[arg-type]


class TestRequireStrDict:
    """`require_str_dict` 边界条件。"""

    def test_valid_dict(self) -> None:
        result = require_str_dict({"a": "b"}, field="m")
        assert dict(result) == {"a": "b"}

    def test_non_mapping_raises(self) -> None:
        with pytest.raises(ValidationError, match="must be Mapping"):
            require_str_dict([("a", "b")], field="m")  # type: ignore[arg-type]

    def test_non_str_value_raises(self) -> None:
        with pytest.raises(ValidationError, match="must be str -> str"):
            require_str_dict({"k": 1}, field="m")  # type: ignore[dict-item]

    def test_non_str_key_raises(self) -> None:
        with pytest.raises(ValidationError, match="must be str -> str"):
            require_str_dict({1: "v"}, field="m")  # type: ignore[dict-item]


class TestRequirePositivePage:
    """`require_positive_page` 边界条件。"""

    def test_none_passes(self) -> None:
        assert require_positive_page(None, field="page") is None

    def test_positive_int_passes(self) -> None:
        assert require_positive_page(3, field="page") == 3

    def test_zero_raises(self) -> None:
        with pytest.raises(ValidationError, match="positive int"):
            require_positive_page(0, field="page")

    def test_negative_raises(self) -> None:
        with pytest.raises(ValidationError, match="positive int"):
            require_positive_page(-1, field="page")

    def test_bool_raises(self) -> None:
        with pytest.raises(ValidationError, match="positive int"):
            require_positive_page(True, field="page")  # type: ignore[arg-type]

    def test_str_raises(self) -> None:
        with pytest.raises(ValidationError, match="positive int"):
            require_positive_page("1", field="page")  # type: ignore[arg-type]


class TestRequireLineRange:
    """`require_line_range` 边界条件。"""

    def test_none_passes(self) -> None:
        assert require_line_range(None, field="lr") is None

    def test_valid_tuple(self) -> None:
        assert require_line_range((2, 5), field="lr") == (2, 5)

    def test_non_tuple_raises(self) -> None:
        with pytest.raises(ValidationError, match="must be \\(int, int\\)"):
            require_line_range([1, 2], field="lr")  # type: ignore[arg-type]

    def test_wrong_length_raises(self) -> None:
        with pytest.raises(ValidationError, match="must be \\(int, int\\)"):
            require_line_range((1, 2, 3), field="lr")  # type: ignore[arg-type]

    def test_start_gt_end_raises(self) -> None:
        with pytest.raises(ValidationError, match="1 <= start <= end"):
            require_line_range((5, 3), field="lr")

    def test_start_zero_raises(self) -> None:
        with pytest.raises(ValidationError, match="1 <= start <= end"):
            require_line_range((0, 5), field="lr")

    def test_non_int_start_raises(self) -> None:
        with pytest.raises(ValidationError, match="lr\\[0\\] must be int"):
            require_line_range(("1", 5), field="lr")  # type: ignore[arg-type]

    def test_non_int_end_raises(self) -> None:
        with pytest.raises(ValidationError, match="lr\\[1\\] must be int"):
            require_line_range((1, "5"), field="lr")  # type: ignore[arg-type]

    def test_bool_start_raises(self) -> None:
        with pytest.raises(ValidationError, match="lr\\[0\\] must be int"):
            require_line_range((True, 5), field="lr")  # type: ignore[arg-type]
