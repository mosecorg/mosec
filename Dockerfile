ARG base=nvidia/cuda:11.6.2-cudnn8-runtime-ubuntu20.04

FROM ${base}

ENV DEBIAN_FRONTEND=noninteractive LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
ENV PATH /opt/conda/bin:$PATH

ARG CONDA_VERSION=py310_23.3.1-0

RUN apt update && \
    apt install -y --no-install-recommends \
        wget \
        git \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN set -x && \
    UNAME_M="$(uname -m)" && \
    if [ "${UNAME_M}" = "x86_64" ]; then \
        MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-${CONDA_VERSION}-Linux-x86_64.sh"; \
        SHA256SUM="aef279d6baea7f67940f16aad17ebe5f6aac97487c7c03466ff01f4819e5a651"; \
    elif [ "${UNAME_M}" = "s390x" ]; then \
        MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-${CONDA_VERSION}-Linux-s390x.sh"; \
        SHA256SUM="ed4f51afc967e921ff5721151f567a4c43c4288ac93ec2393c6238b8c4891de8"; \
    elif [ "${UNAME_M}" = "aarch64" ]; then \
        MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-${CONDA_VERSION}-Linux-aarch64.sh"; \
        SHA256SUM="6950c7b1f4f65ce9b87ee1a2d684837771ae7b2e6044e0da9e915d1dee6c924c"; \
    elif [ "${UNAME_M}" = "ppc64le" ]; then \
        MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-${CONDA_VERSION}-Linux-ppc64le.sh"; \
        SHA256SUM="b3de538cd542bc4f5a2f2d2a79386288d6e04f0e1459755f3cefe64763e51d16"; \
    fi && \
    wget "${MINICONDA_URL}" -O miniconda.sh -q && \
    echo "${SHA256SUM} miniconda.sh" > shasum && \
    if [ "${CONDA_VERSION}" != "latest" ]; then sha256sum --check --status shasum; fi && \
    mkdir -p /opt && \
    bash miniconda.sh -b -p /opt/conda && \
    rm miniconda.sh shasum && \
    ln -s /opt/conda/etc/profile.d/conda.sh /etc/profile.d/conda.sh && \
    echo ". /opt/conda/etc/profile.d/conda.sh" >> ~/.bashrc && \
    echo "conda activate base" >> ~/.bashrc && \
    find /opt/conda/ -follow -type f -name '*.a' -delete && \
    find /opt/conda/ -follow -type f -name '*.js.map' -delete && \
    /opt/conda/bin/conda clean -afy

ENV PYTHON_PREFIX=/opt/conda/bin

RUN update-alternatives --install /usr/bin/python python ${PYTHON_PREFIX}/python 1 && \
    update-alternatives --install /usr/bin/python3 python3 ${PYTHON_PREFIX}/python3 1 && \
    update-alternatives --install /usr/bin/pip pip ${PYTHON_PREFIX}/pip 1 && \
    update-alternatives --install /usr/bin/pip3 pip3 ${PYTHON_PREFIX}/pip3 1

RUN pip install mosec

RUN mkdir -p /workspace
WORKDIR /workspace

ENTRYPOINT [ "bash" ]
