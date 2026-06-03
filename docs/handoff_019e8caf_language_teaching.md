# Handoff: 019e8caf Language Teaching Session

Date: 2026-06-03

Source session:
`/home/asuka/.codex/sessions/2026/06/03/rollout-2026-06-03T16-52-33-019e8caf-3818-7ba3-874c-d1d6d37bae4f.jsonl`

## Current State

- Current branch: `feat/language-teaching`
- Current HEAD: `4ec9b11 fix(frontend): skip auto tts for quiz responses`
- The target Codex session failed to auto-compact near 70% usage.
- This file is the compressed continuation context for that session.

## User Goal In That Session

Build and test the language teaching feature based on `docs/edu/语言教学设计.md`.

Main product goals:

- Add English and Japanese teacher personas.
- Support language level selection.
- Support correction cards and quiz cards.
- Support target-language TTS playback.
- Keep chat streaming stable when tools are used.
- Avoid verbose quiz content being automatically read aloud.

## Completed Commits

`1655449 feat(edu): add language teaching workflow`

- Added language teaching workflow.
- Added `english_teacher` and `japanese_teacher` presets.
- Added language tools and schemas:
  - `correct_text`
  - `generate_quiz`
- Added persona-aware tool routing.
- Added language learning frontend view and cards.
- Added TTS route/config integration.
- Added tests for presets, dispatch, tools, routes, and language flow.

`348a7fa fix(edu): suppress language tool json in chat stream`

- Fixed raw language-tool JSON being shown in chat text.
- WebSocket now filters language tool JSON from streamed assistant text.
- Structured data still reaches frontend via `tool.result`.
- Verification reported in the session:
  - `uv run pytest -q`: 42 passed
  - `ruff`: passed
  - `mypy`: passed
  - `pnpm --dir frontend build`: passed

`fdd6ae5 feat(frontend): render markdown in chat messages`

- Added `frontend/src/components/chat/MarkdownText.vue`.
- Updated chat bubble rendering to support common Markdown.
- Renderer escapes HTML before Markdown conversion.
- Verification:
  - `pnpm --dir frontend build`: passed
  - `/learn` returned 200.

`4ec9b11 fix(frontend): skip auto tts for quiz responses`

- Quiz generation no longer auto-reads the whole long quiz response.
- Per-question TTS buttons remain available.
- Normal short replies and correction feedback can still auto-read.
- Verification:
  - `pnpm --dir frontend build`: passed

## Bugs Already Diagnosed And Fixed

`language must be 'english' or 'japanese'`

- Cause: model passed Chinese aliases such as `英语` or `选择题`.
- Fix: language and quiz type aliases are normalized before validation.
- Tests were added for Chinese alias handling.

`This response_format type is unavailable now`

- Cause: DeepSeek did not support LangChain `with_structured_output` /
  `response_format` in the language tool's internal LLM call.
- Fix: language tools now use normal LLM JSON output, extract JSON manually, and
  validate with Pydantic.
- Fallback structured result prevents unpaired tool calls from polluting the
  conversation checkpoint.

`assistant message with tool_calls must be followed by tool messages`

- Cause: a failed tool call left an incomplete tool-call chain in the same
  conversation checkpoint.
- Fix: ensure tools always return a structured response; user should use a new
  browser conversation after backend fixes.

Raw JSON shown in chat

- Cause: assistant text repeated the tool JSON while frontend also rendered the
  structured card.
- Fix: WebSocket layer filters complete language-tool JSON blocks from chat
  text while preserving `tool.result`.

## Last Unfinished User Request

User requested three TTS behavior fixes:

1. Fill-in-the-blank underscores such as `___` should not be read repeatedly.
2. Card read buttons should use the model/Live2D TTS path, not a separate direct
   audio path.
3. Quiz auto-read suppression should not silence the whole response; it should
   preserve non-question intro/outro text and skip only long question content.

The session implemented these changes and ran `pnpm --dir frontend build`
successfully, but it was interrupted before the intended independent commit.

## Uncommitted Language-TTS Changes

Files currently changed for the unfinished TTS request:

- `frontend/src/components/language/CorrectionCard.vue`
- `frontend/src/components/language/QuizCard.vue`
- `frontend/src/composables/useChatSocket.ts`
- `frontend/src/composables/useTtsAudio.ts`
- `frontend/src/composables/modelSpeech.ts` (new)

Behavior implemented:

- Added a model speech event bus in `modelSpeech.ts`.
- `CorrectionCard` and `QuizCard` call `requestModelSpeech(...)` instead of
  directly calling `postTts(...)`.
- `useChatSocket` listens for `asuka:model-speech` and routes manual card
  playback through the shared Live2D/TTS queue.
- `useTtsAudio` accepts an optional language for queued speech and forwards it
  to `postTts`.
- TTS cleanup replaces repeated underscores with `blank`.
- Quiz response handling tracks `quizTtsMode` and tries to read intro/outro
  while skipping question body.

Known concern before committing:

- `CorrectionCard` and `QuizCard` clear their playing state with a fixed
  `window.setTimeout(..., 700)`, not on actual audio completion. This may be
  acceptable as a minimal UI state placeholder, but it is not exact.
- `extractQuizSpeechSegments` uses regex heuristics. It should be manually
  tested with markdown-formatted quiz responses.

Suggested commit after review:

```bash
pnpm --dir frontend build
git add frontend/src/components/language/CorrectionCard.vue \
  frontend/src/components/language/QuizCard.vue \
  frontend/src/composables/modelSpeech.ts \
  frontend/src/composables/useChatSocket.ts \
  frontend/src/composables/useTtsAudio.ts
git commit -m "fix(frontend): route language card speech through model tts"
```

## Current Dirty Worktree Notes

There are unrelated dirty items that should not be included in the language TTS
commit unless the user explicitly asks:

- `README.md`
- old Live2D docs deleted at root and re-added under `docs/live2d/`
- `Frieren.zip`
- `docs/开发启动指南.md`
- `docs/codex_context_compaction_troubleshooting.md`
- this handoff file

Use targeted `git add` only.

## Recommended Next Steps

1. Inspect the five uncommitted frontend TTS files listed above.
2. Run `pnpm --dir frontend build`.
3. Manually test `/learn` in the browser:
   - ask for B1 English multiple-choice quiz;
   - confirm only intro/outro is read automatically;
   - confirm question body is not auto-read;
   - click a question TTS button and confirm Live2D/model TTS path is used;
   - test a fill-in-the-blank question and confirm underscores are not repeated.
4. Commit only the five TTS-related frontend files if behavior is acceptable.

## Important Repo Rules To Preserve

- Use `uv`, not `pip`.
- Keep route files thin; business logic belongs under `core/`.
- Do not commit `.env`, `*.db`, `*.sqlite`, `__pycache__/`, or large unrelated
  resources.
- Do not revert unrelated dirty files.
- Do not push automatically.
