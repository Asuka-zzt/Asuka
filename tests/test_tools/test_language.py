"""语言教学工具。"""

import json

import pytest

from asuka.core.tools.language import correct_text, generate_quiz
from asuka.core.tools.schemas import (
    CorrectionItem,
    CorrectionResult,
    QuizItem,
    QuizSet,
)


async def test_correct_text_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    result = CorrectionResult(
        has_error=True,
        language="english",
        items=[
            CorrectionItem(
                error_type="主谓一致",
                original="I has",
                corrected="I have",
                explanation_zh="主语 I 后应使用 have。",
            )
        ],
        natural_rewrite="I have an apple.",
        annotation="/aɪ hæv ən ˈæpəl/",
        encouragement_zh="这个错误很常见，改掉就自然很多。",
    )
    async def fake_invoke_json_model(schema: type, prompt: str) -> CorrectionResult:
        assert schema is CorrectionResult
        assert "I has a apple." in prompt
        return result

    monkeypatch.setattr(
        "asuka.core.tools.language._invoke_json_model",
        fake_invoke_json_model,
    )

    output = json.loads(
        await correct_text.ainvoke(
            {"text": "I has a apple.", "language": "english", "level": "A2"}
        )
    )

    assert output["has_error"] is True
    assert output["items"][0]["error_type"] == "主谓一致"
    assert output["natural_rewrite"] == "I have an apple."


async def test_generate_quiz_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    result = QuizSet(
        language="japanese",
        level="N5",
        topic="点餐",
        items=[
            QuizItem(
                type="mcq",
                question="すしを___。",
                options=["ください", "います", "です", "ます"],
                answer="ください",
                explanation_zh="点餐时可用 ください 表示“请给我”。",
                annotation="すしをください。sushi o kudasai.",
            )
        ],
    )
    async def fake_invoke_json_model(schema: type, prompt: str) -> QuizSet:
        assert schema is QuizSet
        assert "点餐" in prompt
        return result

    monkeypatch.setattr(
        "asuka.core.tools.language._invoke_json_model",
        fake_invoke_json_model,
    )

    output = json.loads(
        await generate_quiz.ainvoke(
            {
                "language": "japanese",
                "level": "N5",
                "topic": "点餐",
                "quiz_type": "mcq",
                "n": 1,
            }
        )
    )

    assert output["language"] == "japanese"
    assert len(output["items"]) == 1
    assert output["items"][0]["explanation_zh"]


async def test_generate_quiz_accepts_chinese_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = QuizSet(
        language="english",
        level="B1",
        topic="日常对话",
        items=[
            QuizItem(
                type="mcq",
                question="How are you?",
                options=["I'm fine.", "At 7.", "Blue.", "No."],
                answer="I'm fine.",
                explanation_zh="日常问候 How are you? 可回答 I'm fine.",
                annotation="/haʊ ɑːr juː/",
            )
        ],
    )
    async def fake_invoke_json_model(schema: type, prompt: str) -> QuizSet:
        assert schema is QuizSet
        assert "语言：english" in prompt
        assert "题型：mcq" in prompt
        return result

    monkeypatch.setattr(
        "asuka.core.tools.language._invoke_json_model",
        fake_invoke_json_model,
    )

    output = json.loads(
        await generate_quiz.ainvoke(
            {
                "language": "英语",
                "level": "B1",
                "topic": "日常对话",
                "quiz_type": "选择题",
                "n": 1,
            }
        )
    )

    assert output["language"] == "english"
    assert output["items"][0]["type"] == "mcq"


async def test_generate_quiz_rejects_bad_n() -> None:
    with pytest.raises(ValueError, match="between 1 and 10"):
        await generate_quiz.ainvoke(
            {
                "language": "english",
                "level": "A1",
                "topic": "daily",
                "quiz_type": "mcq",
                "n": 99,
            }
        )
