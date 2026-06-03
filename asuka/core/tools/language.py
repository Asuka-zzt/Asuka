"""语言教学工具：结构化纠错与练习生成。"""

import json
from typing import Any, cast

from langchain_core.tools import tool
from pydantic import BaseModel

from asuka.api.provider import get_llm
from asuka.config import get_settings
from asuka.core.tools.schemas import (
    CorrectionResult,
    LanguageCode,
    QuizItem,
    QuizSet,
    QuizType,
)

_CHECKLISTS: dict[str, str] = {
    "english": "冠词 a/an/the、时态、单复数与可数性、介词搭配、主谓一致",
    "japanese": "助词 は/が/を/に/で、です・ます 敬体、敬语、自他动词、授受动词、长短音与促音",
}

_LANGUAGE_ALIASES: dict[str, LanguageCode] = {
    "english": "english",
    "en": "english",
    "英语": "english",
    "英文": "english",
    "japanese": "japanese",
    "ja": "japanese",
    "jp": "japanese",
    "日语": "japanese",
    "日文": "japanese",
    "日本語": "japanese",
}

_QUIZ_TYPE_ALIASES: dict[str, QuizType] = {
    "mcq": "mcq",
    "multiple_choice": "mcq",
    "multiple choice": "mcq",
    "choice": "mcq",
    "选择题": "mcq",
    "选择": "mcq",
    "cloze": "cloze",
    "blank": "cloze",
    "fill_blank": "cloze",
    "fill in the blank": "cloze",
    "填空题": "cloze",
    "填空": "cloze",
    "translation": "translation",
    "translate": "translation",
    "翻译题": "translation",
    "翻译": "translation",
}


def _validate_language(language: str) -> LanguageCode:
    normalized = language.strip().lower()
    if normalized in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[normalized]
    compact = normalized.replace("-", "_")
    if compact in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[compact]
    if language.strip() in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[language.strip()]
    else:
        raise ValueError("language must be 'english' or 'japanese'")


def _validate_quiz_type(quiz_type: str) -> QuizType:
    normalized = quiz_type.strip().lower().replace("-", "_")
    if normalized in _QUIZ_TYPE_ALIASES:
        return _QUIZ_TYPE_ALIASES[normalized]
    if quiz_type.strip() in _QUIZ_TYPE_ALIASES:
        return _QUIZ_TYPE_ALIASES[quiz_type.strip()]
    else:
        raise ValueError("quiz_type must be 'mcq', 'cloze', or 'translation'")


def _as_tool_json(result: BaseModel | dict[str, object]) -> str:
    """把结构化结果转成 ToolMessage 可安全承载的 JSON 字符串。"""
    payload = result.model_dump() if isinstance(result, BaseModel) else result
    return json.dumps(payload, ensure_ascii=False)


def _message_text(message: Any) -> str:
    """提取 LangChain message 中的文本内容。"""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content)


def _extract_json_object(text: str) -> dict[str, Any]:
    """从模型文本中提取第一个 JSON object。"""
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.strip("`")
        if clean.lower().startswith("json"):
            clean = clean[4:].strip()

    decoder = json.JSONDecoder()
    for index, char in enumerate(clean):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(clean[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("LLM response did not contain a JSON object")


async def _invoke_json_model(schema: type[BaseModel], prompt: str) -> BaseModel:
    """普通 LLM 调用 + JSON 解析，避免依赖 provider response_format。"""
    llm = get_llm(get_settings().default_model)
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    message = await llm.ainvoke(
        f"{prompt}\n\n"
        "只返回一个 JSON object，不要输出 Markdown，不要输出解释文字。\n"
        f"JSON Schema:\n{schema_json}"
    )
    data = _extract_json_object(_message_text(message))
    return schema.model_validate(data)


def _fallback_correction(text: str, language: LanguageCode) -> CorrectionResult:
    """工具失败时返回结构化兜底，保证 tool call 被完整响应。"""
    return CorrectionResult(
        has_error=False,
        language=language,
        items=[],
        natural_rewrite=text,
        annotation="",
        encouragement_zh="这次批改工具暂时没有生成详细结果，请换个说法再试一次。",
    )


def _fallback_quiz(
    language: LanguageCode,
    level: str,
    topic: str,
    quiz_type: QuizType,
) -> QuizSet:
    """工具失败时返回一题兜底练习，避免污染 LangGraph tool call 状态。"""
    sample = (
        QuizItem(
            type=quiz_type,
            question="What do you usually say when you meet a friend?",
            options=["Hello!", "Goodbye!", "Thanks!", "Sorry!"]
            if quiz_type == "mcq"
            else None,
            answer="Hello!",
            explanation_zh="见到朋友时，最基础的日常问候可以说 Hello。",
            annotation="/həˈloʊ/",
        )
        if language == "english"
        else QuizItem(
            type=quiz_type,
            question="友だちに会ったとき、何と言いますか。",
            options=["こんにちは", "さようなら", "ありがとう", "すみません"]
            if quiz_type == "mcq"
            else None,
            answer="こんにちは",
            explanation_zh="见到朋友时，常用 こんにちは 打招呼。",
            annotation="こんにちは。konnichiwa.",
        )
    )
    return QuizSet(language=language, level=level, topic=topic, items=[sample])


@tool
async def correct_text(
    text: str,
    language: str,
    level: str | None = None,
) -> str:
    """批改目标语文本，返回逐条纠错、地道改写、中文讲解和发音标注。"""
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("text must not be empty")

    lang = _validate_language(language)
    annotation_rule = "提供 IPA 音标或简短发音提示" if lang == "english" else "提供假名读法和罗马音"
    prompt = (
        "你是面向中文母语者的语言老师。请批改下面的目标语文本，并严格返回结构化结果。\n"
        f"语言：{lang}\n"
        f"水平：{level or '未指定'}\n"
        f"纠错重点：{_CHECKLISTS[lang]}\n"
        f"标注规则：{annotation_rule}\n"
        "要求：解释一律中文；改写使用目标语；只批改当前文本，不扩展成课程。\n\n"
        f"待批改文本：{clean_text}"
    )
    try:
        result = cast(CorrectionResult, await _invoke_json_model(CorrectionResult, prompt))
    except Exception:
        result = _fallback_correction(clean_text, lang)
    return _as_tool_json(result)


@tool
async def generate_quiz(
    language: str,
    level: str,
    topic: str = "日常",
    quiz_type: str = "mcq",
    n: int = 5,
) -> str:
    """按语言、水平、主题和题型生成练习题。"""
    lang = _validate_language(language)
    qtype = _validate_quiz_type(quiz_type)
    if n < 1 or n > 10:
        raise ValueError("n must be between 1 and 10")

    clean_topic = topic.strip() or "日常"
    annotation_rule = (
        "每题提供 IPA 音标或简短发音提示"
        if lang == "english"
        else "每题提供假名读法和罗马音"
    )
    type_rule = {
        "mcq": "选择题必须提供至少 4 个选项，并只有 1 个正确答案。",
        "cloze": "填空题题干必须包含 ___ 作为空缺。",
        "translation": "翻译题不提供 options，answer 给目标语参考答案。",
    }[qtype]
    prompt = (
        "你是面向中文母语者的语言老师。请生成练习题，并严格返回结构化结果。\n"
        f"语言：{lang}\n"
        f"水平：{level}\n"
        f"主题：{clean_topic}\n"
        f"题型：{qtype}\n"
        f"数量：{n}\n"
        f"题型规则：{type_rule}\n"
        f"标注规则：{annotation_rule}\n"
        "要求：每题包含中文解析；题目难度匹配水平；不要生成超纲长句。"
    )
    try:
        result = cast(QuizSet, await _invoke_json_model(QuizSet, prompt))
    except Exception:
        result = _fallback_quiz(lang, level, clean_topic, qtype)
    return _as_tool_json(result)
