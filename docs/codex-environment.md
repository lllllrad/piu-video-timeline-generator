# Codex development environment

This document covers launching Codex with the project tools and optional
checkout-local configuration. Normal project setup is described in
[development](development.md).

From the repository root, install the tools and dependencies, then launch Codex
inside the mise environment:

```sh
mise install
mise exec -- pnpm install --frozen-lockfile
mise exec -- codex
```

The session's child commands inherit the tool environment. Run `just check`,
`pnpm` and Git commits directly within that session. Restart Codex after changing
the tool configuration so subsequent commands inherit the updated environment.

## Optional checkout-local setup

Run the Codex-only setup explicitly through `sh`:

```sh
sh scripts/setup-codex.sh
```

If the required tools are not installed, allow the script to install the versions in `mise.toml` under `.local/`:

```sh
PIU_USE_MISE=1 sh scripts/setup-codex.sh
```

The setup creates the Python environment, verifies the project and generates a Git-ignored `.codex/config.toml` for the current checkout. The configuration contains checkout-specific absolute paths so Codex can find project-local tools and caches.

## Shell execution

Use non-login shell calls (`login: false`). Login profiles can replace the configured PATH and hide project-local tools.

Once the generated configuration is loaded, commands can run directly:

```sh
just check
just auto '/absolute/path/to/video.mp4'
```

Restart Codex after generating or changing its checkout-local configuration.

## Generated configuration

Do not hand-edit or commit `.codex/config.toml` as a portable project setting. Change `scripts/configure_codex.py` when the generated defaults need to change. Preserve existing user customizations; the generator intentionally stops instead of overwriting a customized file.

Run the generator again after moving a checkout:

```sh
.venv/bin/python scripts/configure_codex.py
```

## Sandboxes and network access

Dependency installation, YouTube access, macOS Vision execution and writes to protected paths may require explicit Codex approval. Request the required permission rather than bypassing the sandbox. Local media analysis and the normal test suite should remain usable without network access after setup.

Project configuration changes command environment only. It does not change project trust, sandbox policy or approval requirements.
