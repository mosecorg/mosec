#!/bin/sh
set -e
eval "$(conda shell.bash hook)"

# Support multiple python versions
for VERSION in 3.6 3.7 3.8 3.9; do
  conda create -y -n py$VERSION python=$VERSION
  conda activate py$VERSION

  pip install --no-cache-dir setuptools wheel
  PRODUCTION_MODE=yes python setup.py bdist_wheel --plat-name manylinux1_x86_64

  conda deactivate
  rm -rf build
done
