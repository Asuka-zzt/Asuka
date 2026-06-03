"""Live2DTagExtractor 增量解析回归测试。

回归点：LLM 以逐字符/细粒度流式输出标签时，标签常被分片切在中间（buffer 只剩
'[' 或 '[exp'）。旧实现只在 rest 已是完整 '[emotion:'/'[expression:' 前缀时才缓冲，
否则把 '[' 当普通字符吐出，导致标签被永久打断 —— 前端收不到任何 live2d.emotion 事件，
聊天文本里还残留原始标签。
"""

from collections.abc import Iterable

from asuka.routes.ws import Live2DTagExtractor


def _run(chunks: Iterable[str]) -> tuple[str, list[dict]]:
    ex = Live2DTagExtractor()
    clean: list[str] = []
    events: list[dict] = []
    for c in chunks:
        text, evts = ex.feed(c)
        clean.append(text)
        events.extend(evts)
    clean.append(ex.flush())
    return "".join(clean), events


_SAMPLE = "诶……怎么样[expression:ku] 天气好。[emotion:happy][expression:yy] 完[expression:anya2]"
_EXPECTED_CLEAN = "诶……怎么样 天气好。 完"
_EXPECTED_EVENTS = [
    {"type": "live2d.emotion", "expression": "ku"},
    {"type": "live2d.emotion", "emotion": "happy"},
    {"type": "live2d.emotion", "expression": "yy"},
    {"type": "live2d.emotion", "expression": "anya2"},
]


def test_extracts_tags_when_streamed_char_by_char() -> None:
    # 逐字符喂入：必然把每个标签切成多个分片，是真实 LLM 流式的最坏情况。
    clean, events = _run(list(_SAMPLE))
    assert events == _EXPECTED_EVENTS
    assert clean == _EXPECTED_CLEAN


def test_extracts_tags_in_one_shot() -> None:
    clean, events = _run([_SAMPLE])
    assert events == _EXPECTED_EVENTS
    assert clean == _EXPECTED_CLEAN


def test_split_right_after_bracket() -> None:
    # 对抗性分片：每个 '[' 单独成片，后续内容在下一片 —— 旧实现就是在这里丢标签。
    parts: list[str] = []
    buf = ""
    for ch in _SAMPLE:
        if ch == "[":
            if buf:
                parts.append(buf)
                buf = ""
            parts.append("[")
        else:
            buf += ch
    if buf:
        parts.append(buf)

    clean, events = _run(parts)
    assert events == _EXPECTED_EVENTS
    assert clean == _EXPECTED_CLEAN


def test_literal_brackets_pass_through() -> None:
    # 普通方括号（数组下标、括注）不能被误吞或误判为标签。
    clean, events = _run(list("arr[0] 和 [备注] 都在"))
    assert events == []
    assert clean == "arr[0] 和 [备注] 都在"


def test_unknown_and_malformed_tags_pass_through() -> None:
    # 未知标签、非法 emotion 值原样保留为文本，不产生事件。
    clean, events = _run(list("前[foobar:x]中[emotion:unknown]后"))
    assert events == []
    assert clean == "前[foobar:x]中[emotion:unknown]后"


def test_trailing_partial_tag_is_flushed() -> None:
    # 流结束时仍停在半个标签里：flush 应把它作为文本吐出，不丢字符。
    clean, events = _run(list("结尾["))
    assert events == []
    assert clean == "结尾["
