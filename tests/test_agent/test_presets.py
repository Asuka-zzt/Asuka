"""语言教学 persona 预置。"""

import pytest

from asuka.core.agent.presets import (
    english_teacher,
    japanese_teacher,
    resolve_agent_config,
)


def test_english_teacher_preset() -> None:
    cfg = english_teacher("A2")

    assert cfg.id == "english_teacher"
    assert cfg.language == "english"
    assert cfg.level == "A2"
    assert "中文" in cfg.soul
    assert "冠词" in cfg.soul
    assert "时态" in cfg.soul
    assert "IPA" in cfg.soul


def test_japanese_teacher_preset() -> None:
    cfg = japanese_teacher("N5")

    assert cfg.id == "japanese_teacher"
    assert cfg.language == "japanese"
    assert cfg.level == "N5"
    assert "中文" in cfg.soul
    assert "助词" in cfg.soul
    assert "假名" in cfg.soul
    assert "罗马音" in cfg.soul


def test_resolve_agent_config_rejects_unknown_persona() -> None:
    with pytest.raises(ValueError, match="unknown persona_id"):
        resolve_agent_config("bad", None)
