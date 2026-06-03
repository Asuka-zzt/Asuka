"""语言教学工具的结构化输出 schema。"""

from typing import Literal

from pydantic import BaseModel, Field

LanguageCode = Literal["english", "japanese"]
QuizType = Literal["mcq", "cloze", "translation"]


class CorrectionItem(BaseModel):
    """单条纠错说明。"""

    error_type: str = Field(description="错误类型，如 冠词 / 时态 / 助词")
    original: str = Field(description="原始错误片段")
    corrected: str = Field(description="修正后的片段")
    explanation_zh: str = Field(description="中文解释")


class CorrectionResult(BaseModel):
    """批改结果。"""

    has_error: bool
    language: LanguageCode
    items: list[CorrectionItem]
    natural_rewrite: str
    annotation: str
    encouragement_zh: str


class QuizItem(BaseModel):
    """单道练习题。"""

    type: QuizType
    question: str
    options: list[str] | None = None
    answer: str
    explanation_zh: str
    annotation: str


class QuizSet(BaseModel):
    """一组练习题。"""

    language: LanguageCode
    level: str
    topic: str
    items: list[QuizItem]
