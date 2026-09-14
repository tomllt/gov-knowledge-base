"""`HeadingPath` 模型测试。"""

from __future__ import annotations

import pytest

from p1_core.exceptions import SerializationError, ValidationError
from p1_core.models.heading import HeadingPath


class TestHeadingPathConstruction:
    """构造与基本属性。"""

    def test_root_creates_single_level_path(self) -> None:
        path = HeadingPath.root("第 1 章 总则")
        assert path.depth() == 1
        assert path.parts == ("第 1 章 总则",)

    def test_child_appends_level(self) -> None:
        path = HeadingPath.root("第 1 章").child("1.1 适用范围").child("1.1.1 概述")
        assert path.depth() == 3
        assert path.parts == ("第 1 章", "1.1 适用范围", "1.1.1 概述")

    def test_path_is_immutable(self) -> None:
        path = HeadingPath.root("A")
        with pytest.raises((AttributeError, Exception)):
            path.parts = ("B",)  # type: ignore[misc]

    def test_two_paths_with_same_parts_are_equal(self) -> None:
        a = HeadingPath(("第 1 章", "1.1"))
        b = HeadingPath(("第 1 章", "1.1"))
        assert a == b
        assert hash(a) == hash(b)


class TestHeadingPathValidation:
    """空值/类型校验。"""

    def test_empty_parts_raises(self) -> None:
        with pytest.raises(ValidationError, match="parts must not be empty"):
            HeadingPath(())

    @pytest.mark.parametrize("bad_value", ["", "   ", "\t\n"])
    def test_blank_part_raises(self, bad_value: str) -> None:
        with pytest.raises(ValidationError, match="must be non-empty"):
            HeadingPath(("ok", bad_value))

    def test_non_string_part_raises(self) -> None:
        with pytest.raises(ValidationError, match="must be non-empty str"):
            HeadingPath(("ok", 42))  # type: ignore[arg-type]

    def test_root_blank_raises(self) -> None:
        with pytest.raises(ValidationError):
            HeadingPath.root("")


class TestHeadingPathSerialization:
    """序列化往返。"""

    def test_to_dict_format(self) -> None:
        path = HeadingPath(("第 1 章", "1.1"))
        assert path.to_dict() == {"parts": ["第 1 章", "1.1"]}

    def test_from_dict_roundtrip(self) -> None:
        original = HeadingPath(("第 1 章", "1.1", "1.1.1"))
        restored = HeadingPath.from_dict(original.to_dict())
        assert restored == original

    def test_from_dict_invalid_parts_raises(self) -> None:
        with pytest.raises(SerializationError, match="must be list"):
            HeadingPath.from_dict({"parts": "not-a-list"})

    def test_from_dict_rejects_non_string_parts(self) -> None:
        with pytest.raises(SerializationError, match="must be list\\[str\\]"):
            HeadingPath.from_dict({"parts": ["第 1 章", 2]})

    def test_from_dict_missing_parts_raises(self) -> None:
        with pytest.raises(SerializationError, match="must be list"):
            HeadingPath.from_dict({})


class TestHeadingPathStringification:
    """路径字符串输出。"""

    def test_as_path_string_default_separator(self) -> None:
        path = HeadingPath(("第 1 章", "1.1"))
        assert path.as_path_string() == "第 1 章 / 1.1"

    def test_as_path_string_custom_separator(self) -> None:
        path = HeadingPath(("A", "B"))
        assert path.as_path_string(sep=" > ") == "A > B"
