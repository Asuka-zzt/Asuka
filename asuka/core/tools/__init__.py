"""工具层：LangChain @tool 定义与按 Agent 分配的注册表。"""

from asuka.core.tools.registry import get_tools_for_agent
from asuka.core.tools.schemas import CorrectionResult, QuizSet

__all__ = ["CorrectionResult", "QuizSet", "get_tools_for_agent"]
