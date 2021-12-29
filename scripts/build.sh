#!/bin/sh
set -e

export PATH=$HOME/miniconda3/bin:$PATH
which conda
eval "$(conda shell.bash hook)"
source ${HOME}/.bashrc

OS_NAME=$(uname -s)

# Support multiple python versions
for VERSION in 3.7 3.8 3.9 3.10; do
  conda create -y -n py$VERSION python=$VERSION
  conda activate py$VERSION
  which python

  ${HOME}/miniconda3/envs/py${VERSION}/bin/pip install --no-cache-dir setuptools wheel

  if [[ "${OS_NAME}" == "Linux" ]]; then
    PRODUCTION_MODE=yes RUST_TARGET=x86_64-unknown-linux-gnu \
      ${HOME}/miniconda3/envs/py${VERSION}/bin/python setup.py sdist bdist_wheel --plat-name manylinux1_x86_64 # linux
  else
    PRODUCTION_MODE=yes RUST_TARGET=x86_64-apple-darwin \
      ${HOME}/miniconda3/envs/py${VERSION}/bin/python setup.py sdist bdist_wheel --plat-name macosx_10.9_x86_64 # macos
  fi

  conda deactivate
  rm -rf build
done
