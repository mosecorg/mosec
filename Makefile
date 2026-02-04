PY_SOURCE_FILES=mosec tests examples
RUST_SOURCE_FILES=src/*
RUST_BACKTRACE=1

install_py:
	uv venv
	uv sync --all-groups --all-extras
	uv run -- prek install

install_rs:
	rustup toolchain install nightly --no-self-update
	rustup component add rustfmt clippy --toolchain nightly

install: install_py install_rs

test:
	echo "Running tests for the main logic and mixin(!shm)"
	uv run -- pytest tests -vv -s -m "not shm"
	cargo test -vv

test_unit:
	echo "Running tests for the main logic"
	uv run -- pytest -vv -s tests/test_log.py tests/test_protocol.py tests/test_coordinator.py
	cargo test -vv

test_shm:
	echo "Running tests for the shm mixin"
	uv run -- pytest tests -vv -s -m "shm"

test_all:
	echo "Running tests for the all features"
	uv run -- pytest tests -vv -s
	cargo test -vv

test_chaos:
	@uv run -m tests.bad_req

doc:
	@cd docs && make html && cd ../
	@uv run -m http.server -d docs/build/html 7291 -b 127.0.0.1

clean:
	@cargo clean
	@uv cache clean
	@-rm -rf build/ dist/ .eggs/ site/ *.egg-info .pytest_cache .mypy_cache .ruff_cache
	@-find . -name '*.pyc' -type f -exec rm -rf {} +
	@-find . -name '__pycache__' -exec rm -rf {} +

package:
	uv run -- maturin build --release --out dist

publish: package
	uv run -- twine upload dist/*

format:
	@uv run -- ruff check --fix ${PY_SOURCE_FILES}
	@uv run -- ruff format ${PY_SOURCE_FILES}
	@cargo +nightly fmt --all

lint:
	@uv run -- ruff check ${PY_SOURCE_FILES}
	@uv run -- ruff format --check ${PY_SOURCE_FILES}
	@-rm mosec/_version.py
	@uv run -- pyright --stats
	@uv run -- mypy --non-interactive --install-types ${PY_SOURCE_FILES}
	@cargo +nightly fmt -- --check

semantic_lint:
	@cargo clippy -- -D warnings

version:
	@cargo metadata --format-version 1 | jq -r '.packages[] | select(.name == "mosec") | .version'

add_license:
	@addlicense -c "MOSEC Authors" **/*.py **/*.rs **/**/*.py

dep_license:
	@cargo license --direct-deps-only --authors --avoid-build-deps --avoid-dev-deps --do-not-bundle --all-features --json > license.json

.PHONY: test doc
