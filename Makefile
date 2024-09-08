.DEFAULT_GOAL:=dev

PY_SOURCE_FILES=mosec tests examples setup.py
RUST_SOURCE_FILES=src/*

install:
	pip install -e .[dev,doc,mixin]
	pre-commit install
	rustup toolchain install nightly
	rustup component add rustfmt --toolchain nightly

dev:
	cargo build
	@mkdir -p mosec/bin
	@cp ./target/debug/mosec mosec/bin/mosec
	pip install -e .[dev]

test: dev
	@pip install -q -r requirements/mixin.txt
	echo "Running tests for the main logic and mixin(!shm)"
	pytest tests -vv -s -m "not shm"
	RUST_BACKTRACE=1 cargo test -vv

test_unit: dev
	echo "Running tests for the main logic"
	pytest -vv -s tests/test_log.py tests/test_protocol.py tests/test_coordinator.py
	RUST_BACKTRACE=1 cargo test -vv

test_shm: dev
	@pip install -q -r requirements/mixin.txt
	echo "Running tests for the shm mixin"
	pytest tests -vv -s -m "shm"
	pip uninstall -y -r requirements/mixin.txt

test_all: dev
	@pip install -q -r requirements/mixin.txt
	echo "Running tests for the all features"
	pytest tests -vv -s
	RUST_BACKTRACE=1 cargo test -vv

test_chaos: dev
	@python -m tests.bad_req

doc:
	@cd docs && make html && cd ../
	@python -m http.server -d docs/build/html 7291 -b 127.0.0.1

clean:
	@cargo clean
	@-rm -rf build/ dist/ .eggs/ site/ *.egg-info .pytest_cache .mypy_cache .ruff_cache
	@-rm -rf mosec/bin/
	@-find . -name '*.pyc' -type f -exec rm -rf {} +
	@-find . -name '__pycache__' -exec rm -rf {} +

package: clean
	PRODUCTION_MODE=yes python setup.py bdist_wheel

cross_compile: clean
	cibuildwheel --platform linux

publish: package
	twine upload dist/*

format:
	@ruff check --fix ${PY_SOURCE_FILES}
	@ruff format ${PY_SOURCE_FILES}
	@cargo +nightly fmt --all

lint:
	@pip install -q -e .
	@ruff check ${PY_SOURCE_FILES}
	@-rm mosec/_version.py
	@pyright --stats
	@mypy --non-interactive --install-types ${PY_SOURCE_FILES}
	@cargo +nightly fmt -- --check

semantic_lint:
	@cargo clippy -- -D warnings

version:
	@python -m setuptools_scm

add_license:
	@addlicense -c "MOSEC Authors" **/*.py **/*.rs **/**/*.py

dep_license:
	@cargo license --direct-deps-only --authors --avoid-build-deps --avoid-dev-deps --do-not-bundle --all-features --json > license.json

.PHONY: test doc
