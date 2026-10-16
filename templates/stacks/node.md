# Node / TypeScript — stack opinions (read by reef-init, never copied)
- Layout: `src/` for product code, `tests/` or `*.test.ts` beside the module; one package per deployable; `index.ts` re-exports, never logic.
- Package manager: the lockfile decides (`package-lock.json` → `npm ci`, `pnpm-lock.yaml` → `pnpm install --frozen-lockfile`); never mix.
- Tests: Vitest or Jest with `describe/it`; one golden-output test per user-visible output; `npm test` is the full gate, a fast subset is `gates.fast`.
- Types: `strict: true` in tsconfig; no `any` in product code without a `// why:` comment; types generated from the schema, never hand-copied.
- Lint and format: ESLint + Prettier through `npm run lint` / `npm run format`; CI fails on either; no `eslint-disable` without a reason.
- Env and config: `.env.example` holds every key; `process.env` read in one module; ports and hosts parameterised.
- Generated code (ORM clients, API clients): regenerated per worktree by `worktree.setup`, never committed, never restored under a running server.
- Errors: throw typed errors; no swallowed promise; `unhandledRejection` is a crash, not a log line.
- Scripts: every `package.json` script is a one-liner that calls a file under `scripts/`; no logic in JSON strings.
