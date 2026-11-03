# Dependency patches

The pnpm workspace declares a patch for QG's nested-configuration discovery.
Generated media, caches, Python environments and build directories are outside
that discovery boundary. Traversing active `.local` builds or temporary test
directories can race with their atomic publication or cleanup.

`pnpm install --frozen-lockfile` applies the patch. Project rules and test checks
remain configured in `.qg.yaml`.
