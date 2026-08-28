# Project workflow

- Read README.md before making changes. This is a Pump It Up video timeline project; chart/replay extraction is a later goal.
- Write all project documentation in English.
- Prefer `just check`, `just fetch ...`, and `just probe ...` when the project Codex environment is loaded. Use non-login shell tool calls (`login: false`). `.codex/config.toml` puts project-local mise shims on PATH and isolates caches in `.local/`.
- If `just` is not found in an existing session, use `./scripts/mise exec -- just ...` until configuration reload. For other development commands, use `./scripts/mise exec -- <command>` or `./scripts/mise run <task>`. Do not rely on shell activation persisting between calls.
- Initial setup: `./scripts/bootstrap`. Do not install into the user's home, use Homebrew, or edit global shell configuration.
- Bootstrap generates Git-ignored `.codex/config.toml` using the current checkout path. Change `scripts/configure_codex.py` for portable defaults, not the generated file. Preserve custom local settings; do not force regeneration over them.
- Keep tool installations, caches, and temporary files in `.local/`. Network-restricted sandboxes may require approval for installation or YouTube access; do not bypass their restrictions.
- Run `just check` (or `./scripts/mise run check`) after changes.
- Keep downloaded videos, comments, credentials, and generated outputs out of Git.
- Comments are noisy reference labels, not ground truth and not detector inputs. Do not tune outputs for exact agreement with them.
- Preserve original media timestamps. Local YouTube Studio exports must remain usable without a network request.
