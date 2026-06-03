"""Wiki 各阶段 prompt 模板。与节点逻辑解耦，便于调参与多语言。

结构化字段（abstractions/relationships/order）由 with_structured_output 约束输出，
prompt 只需描述任务与语言要求，无需再贴 YAML 格式样例。
"""


def _lang_note(language: str) -> str:
    """非英语时追加语言约束。"""
    if language.lower() in ("english", "en"):
        return ""
    return (
        f"\n\n重要：请用「{language}」书写所有生成内容"
        f"（名称、描述、摘要、标签、章节正文）。代码语法与专有名词除外。"
    )


def identify_prompt(project_name: str, context: str, file_listing: str,
                    max_abstractions: int, language: str) -> str:
    """识别核心抽象。"""
    return f"""分析项目 `{project_name}` 的代码库，识别出 5-{max_abstractions} 个最重要的核心抽象，
帮助初学者快速理解这个项目。

代码库内容：
{context}

可用的文件索引与路径：
{file_listing}

对每个抽象给出：
1. 简洁的名称 name。
2. 初学者友好的描述 description（约 100 字，用一个通俗类比解释它是什么）。
3. 相关文件下标列表 file_indices（整数，对应上面的文件索引）。{_lang_note(language)}"""


def analyze_prompt(project_name: str, abstraction_listing: str, context: str,
                   language: str) -> str:
    """分析抽象间关系 + 项目摘要。"""
    return f"""基于项目 `{project_name}` 的以下抽象与相关代码片段：

抽象索引与名称：
{abstraction_listing}

上下文（抽象、描述、代码）：
{context}

请给出：
1. 项目整体目的与功能的高层 summary（几句话，初学者友好，可用 markdown 加粗/斜体）。
2. 关系列表 details，描述这些抽象之间的关键交互。每条关系含：
   - from_abstraction：源抽象索引
   - to_abstraction：目标抽象索引
   - label：交互的简短标签（几个词，如 “管理” / “使用” / “继承”）
确保每个抽象至少出现在一条关系中。{_lang_note(language)}"""


def order_prompt(project_name: str, abstraction_listing: str,
                 relationships_summary: str, language: str) -> str:
    """决定章节教学顺序。"""
    return f"""项目 `{project_name}` 识别出以下抽象，及其关系摘要：

抽象索引与名称：
{abstraction_listing}

关系摘要：
{relationships_summary}

请按最适合初学者循序渐进学习的顺序，输出 chapter_order：
一个抽象索引的列表，从最基础/最先该理解的概念排到最后。
列表必须恰好包含每个抽象索引一次。{_lang_note(language)}"""


def chapter_prompt(project_name: str, chapter_num: int, abstraction_name: str,
                   abstraction_description: str, file_context: str,
                   full_chapter_listing: str, prev_chapter: str, next_chapter: str,
                   language: str) -> str:
    """撰写单个章节（自由 Markdown）。"""
    return f"""为项目 `{project_name}` 撰写教程的第 {chapter_num} 章，
主题是抽象「{abstraction_name}」。

抽象描述：
{abstraction_description}

相关代码：
{file_context}

完整章节目录（用于互相链接）：
{full_chapter_listing}

上一章：{prev_chapter or "（无，这是第一章）"}
下一章：{next_chapter or "（无，这是最后一章）"}

要求：
- 输出一篇完整的 Markdown 章节，以 `# 第 {chapter_num} 章：{abstraction_name}` 作为标题。
- 面向初学者：用通俗类比、循序渐进，配合关键代码片段讲解。
- 适当引用相关文件；在结尾给出与上一章/下一章的过渡与链接。
- 直接输出 Markdown 正文，不要包裹在代码块里。{_lang_note(language)}"""
