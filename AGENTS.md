# Project workflow

- Read README.md before making changes. This is a Pump It Up video timeline project; chart/replay extraction is a later goal.
- Write all project documentation in English.
- Prefer `just check`, `just fetch ...`, and `just probe ...` after bootstrap. Use non-login shell tool calls (`login: false`). Recipes run Python through the project `.venv` and isolate caches in `.local/`.
- Initial setup with system Python 3.12, FFmpeg and Deno: `./scripts/bootstrap`. If those tools are unavailable, opt into project-local pinned tools with `PIU_USE_MISE=1 ./scripts/bootstrap`. Mise installs tools only; pip installs Python packages into `.venv` from the requirements files.
- Bootstrap generates Git-ignored `.codex/config.toml` using the current checkout path. Change `scripts/configure_codex.py` for portable defaults, not the generated file. Preserve custom local settings; do not force regeneration over them.
- Keep tool installations, caches, and temporary files in `.local/`. Network-restricted sandboxes may require approval for installation or YouTube access; do not bypass their restrictions.
- Run `just check` after changes.
- Keep downloaded videos, comments, credentials, and generated outputs out of Git.
- Comments are noisy reference labels, not ground truth and not detector inputs. Do not tune outputs for exact agreement with them.
- Preserve original media timestamps. Local YouTube Studio exports must remain usable without a network request.
