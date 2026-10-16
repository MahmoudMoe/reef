# Rust — stack opinions (read by reef-init, never copied)
- Layout: one workspace, `crates/<name>/` per crate; `src/lib.rs` holds the API, `src/main.rs` only wires it.
- Build and test: `cargo build` / `cargo test -q` are the gates; `cargo clippy -- -D warnings` and `cargo fmt --check` in CI.
- Errors: `Result<T, E>` with `thiserror` in libraries and `anyhow` only at the binary edge; no `unwrap()` outside tests without a `// why:`.
- Unsafe: every `unsafe` block carries a `// SAFETY:` comment and a test that exercises its invariant.
- Dependencies: `Cargo.lock` committed for binaries; features explicit; `cargo deny` or `cargo audit` as a release gate.
- Tests: unit tests in the module, integration tests under `tests/`; a golden-output test per user-visible output.
- Config: environment through one `config` module; no `std::env::var` scattered through the crate.
