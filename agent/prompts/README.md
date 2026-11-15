# Prompts

One versioned Markdown file per node. Front matter holds `node` and `version`; the body uses
`$variables` (Python `string.Template`). Code loads prompts only through `agent/prompts/loader.py`;
CI (`scripts/check_repo.py`) fails if a prompt-like string is found inline in code.
