# Go — stack opinions (read by reef-init, never copied)
- Layout: `cmd/<binary>/main.go` only wires; `internal/` for product packages; no `pkg/` dumping ground.
- Build and test: `go build ./...` / `go test ./...` are the gates; `go vet` and `staticcheck` in CI; `gofmt` enforced.
- Errors: return and wrap with `%w`; never ignore an error with `_` outside tests without a `// why:`; no panics in library code.
- Tests: table-driven `TestXxx` functions; golden files under `testdata/`; a fake per external system, never a live call.
- Dependencies: `go.mod` + `go.sum` committed; `go mod tidy` leaves no diff in CI; `govulncheck` as a release gate.
- Config: one `config` package reading the environment once; ports and hosts parameterised; `context.Context` first argument everywhere.
- Concurrency: every goroutine has an owner and a way to stop; `errgroup` over bare `go` statements.
