# Codex development environment

This document applies only when the repository is opened as a trusted project in Codex. It is not required for normal use or development.

Bootstrap generates a Git-ignored `.codex/config.toml` for the current checkout. The file contains checkout-specific absolute paths and environment variables so Codex can find project-local tools and caches.

## Shell execution

Use non-login shell calls (`login: false`). Login profiles can replace the configured PATH and hide project-local tools.

Once the generated configuration is loaded, commands can run directly:

```sh
just check
just probe '/absolute/path/to/video.mp4'
```

An already-open Codex session may still have the previous environment. Reload the project after bootstrap, or use this fallback in the stale session:

```sh
sh scripts/run.sh just check
```

## Generated configuration

Do not hand-edit or commit `.codex/config.toml` as a portable project setting. Change `scripts/configure_codex.py` when the generated defaults need to change. Preserve existing user customizations; the generator intentionally stops instead of overwriting a customized file.

Run the generator again after moving a checkout:

```sh
.venv/bin/python scripts/configure_codex.py
```

## Sandboxes and network access

Dependency installation, YouTube access, macOS Vision execution and writes to protected paths may require explicit Codex approval. Request the required permission rather than bypassing the sandbox. Local media analysis and the normal test suite should remain usable without network access after setup.

Project configuration changes command environment only. It does not change project trust, sandbox policy or approval requirements.
