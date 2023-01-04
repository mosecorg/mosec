.DEFAULT_GOAL:=dev

PY_SOURCE_FILES=mosec tests examples scripts setup.py
RUST_SOURCE_FILES=src/*

install:
	pip install -e .[dev,doc,plugin]
	pre-commit install
	rustup toolchain install nightly
	rustup component add rustfmt --toolchain nightly

dev:
	cargo build
	@mkdir -p mosec/bin
	@cp ./target/debug/mosec mosec/bin/
	pip install -e .

test: dev
	echo "Running tests for the main logic"
	pytest tests -vv -s -m "not arrow"
	RUST_BACKTRACE=1 cargo test -vv

test_plugin: dev
	@pip install -q -r requirements/plugin.txt
	echo "Running tests for the plugin"
	pytest tests -vv -s -m "arrow"
	pip uninstall -y -r requirements/plugin.txt

test_all: dev
	@pip install -q -r requirements/plugin.txt
	echo "Running tests for the all features"
	pytest tests -vv -s
	RUST_BACKTRACE=1 cargo test -vv

doc:
	mkdocs serve

clean:
	@cargo clean
	@-rm -rf build/ dist/ .eggs/ site/ *.egg-info .pytest_cache .mypy_cache
	@-find . -name '*.pyc' -type f -exec rm -rf {} +
	@-find . -name '__pycache__' -exec rm -rf {} +

package: clean
	PRODUCTION_MODE=yes python setup.py bdist_wheel

cross_compile: clean
	cibuildwheel --platform linux

publish: package
	twine upload dist/*

format:
	@autoflake --in-place --recursive ${PY_SOURCE_FILES}
	@isort --project=mosec ${PY_SOURCE_FILES}
	@black ${PY_SOURCE_FILES}
	@cargo +nightly fmt --all

lint:
	@pip install -q -e .
	isort --check --diff --project=mosec ${PY_SOURCE_FILES}
	black --check --diff ${PY_SOURCE_FILES}
	pylint -j 8 --recursive=y mosec
	pylint -j 8 --recursive=y --disable=import-error examples --generated-members=numpy.*,torch.*,cv2.*,cv.*
	pydocstyle mosec
	@-rm mosec/_version.py
	pyright --stats
	mypy --non-interactive --install-types ${PY_SOURCE_FILES}
	cargo +nightly fmt -- --check

semantic_lint:
	@cargo clippy -- -D warnings

version:
	@python -m setuptools_scm

add_license:
	@addlicense -c "MOSEC Authors" **/*.py **/*.rs **/**/*.py

.PHONY: test doc
