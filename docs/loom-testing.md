# Loom Testing

This project includes [loom](https://github.com/tokio-rs/loom) tests to detect concurrency bugs like deadlocks and data races in the Rust code.

## Background

Loom is a testing tool that can systematically explore different thread interleavings to find concurrency bugs that might not surface in regular testing. These tests were added in response to deadlock issues:

- [#311](https://github.com/mosecorg/mosec/issues/311): deadlock when lots of client requests closed before response
- [#316](https://github.com/mosecorg/mosec/issues/316): deadlock in nested function calls with multiple locks

## Running Loom Tests

To run the loom tests:

```bash
cargo test --features loom tasks::tests::loom_tests
```

## What is Tested

The loom tests focus on the synchronization patterns in `TaskManager` that were prone to deadlocks:

1. **concurrent_task_operations**: Tests the `update_multi_tasks` pattern where tasks are updated and notifications are sent concurrently
2. **concurrent_delete_notify**: Tests concurrent task deletion and notification scenarios  
3. **concurrent_multiple_tasks**: Tests general concurrent operations including adding tasks while others are being notified

## Notes

- Loom tests use a simplified version of `TaskManager` that focuses only on the synchronization primitives
- The tests are only compiled when the `loom` feature is enabled
- Loom is incompatible with tokio/async code, so the tests use simplified synchronous versions of the problematic patterns