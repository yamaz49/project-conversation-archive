# Conversation provider coverage

Read this reference when discovering conversations across assistants.

## Support means readable

Treat an assistant as covered only when this run can enumerate stable conversation IDs and read the relevant turns through an already configured tool, connector, official export, or documented plaintext local index. A product name in this catalog does not imply account access or automatic recovery.

Attempt access in this order:

1. Current app/task APIs or an installed connector.
2. A provider-supported API or official conversation export already available locally.
3. A documented plaintext local history with an existing adapter.
4. A previously registered export location whose identity and format still validate.

Do not install software, sign in, trigger an export, or connect an account without separate user authorization. Do not scrape private cloud endpoints, browser profiles, encrypted stores, or undocumented application databases. Do not crawl the home directory looking for possible histories.

## Provider families

Check these families when their access route is present; future assistants use the same capability rules.

- OpenAI: Codex and ChatGPT.
- Anthropic: Claude and Claude Code.
- Coding assistants: WorkBuddy, Cursor, Windsurf, GitHub Copilot Chat, Gemini Code Assist or Gemini CLI, Kiro, Cline, Roo Code, Continue, and Aider.
- General assistants: Gemini, Microsoft Copilot, Perplexity, DeepSeek, Kimi, Doubao, and Qwen.

Use canonical lowercase provider IDs such as `codex`, `chatgpt`, `claude`, `claude-code`, `workbuddy`, `cursor`, or `gemini`. Keep two products separate when their source IDs or export formats differ; project resolution may merge their conclusions later.

## Known direct routes

- For Codex tasks and ChatGPT conversations exposed by the Codex app, use task/chat listing, archived-task listing, and thread reading capabilities. Listing metadata is not proof that full turn text was readable.
- For Claude Code JSONL, use `scripts/scan_claude_history.py` only on explicit known project/history paths. Its inventory does not itself summarize content.
- For every other assistant, use a currently available connector, supported API, official export, or registered adapter. If none exists, report `not-configured` or `unsupported`; never improvise a private-database parser during an archive run.

## Coverage record

For every attempted provider store:

- `coverage`: `available`, `partially-readable`, `not-configured`, `permission-denied`, or `unsupported`;
- `access_method`: `app-tool`, `connector`, `official-api`, `official-export`, `local-index`, `registered-export`, or `none`;
- `checked_at` and, when known, adapter/export version;
- discovered root-conversation count and readable root-conversation count.

Multiple stores from the same brand may have separate records. A failed provider must not block readable providers. Reuse a still-valid registered route on later runs, but inventory it once per update so newly added conversations are detected.
