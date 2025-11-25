ARG base=nvidia/cuda:13.0.2-cudnn-runtime-ubuntu22.04

FROM ${base}

ENV DEBIAN_FRONTEND=noninteractive LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
ENV PATH /opt/conda/bin:$PATH

ARG CONDA_VERSION=py311_25.9.1-1

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
        SHA256SUM="238abad23f8d4d8ba89dd05df0b0079e278909a36e06955f12bbef4aa94e6131"; \
    elif [ "${UNAME_M}" = "aarch64" ]; then \
        MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-${CONDA_VERSION}-Linux-aarch64.sh"; \
        SHA256SUM="4e0723b9d76aa491cf22511dac36f4fdec373e41d2a243ff875e19b8df39bf94"; \
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
ENV PATH="$PATH:/opt/conda/bin"

RUN update-alternatives --install /usr/bin/python python ${PYTHON_PREFIX}/python 1 && \
    update-alternatives --install /usr/bin/python3 python3 ${PYTHON_PREFIX}/python3 1 && \
    update-alternatives --install /usr/bin/pip pip ${PYTHON_PREFIX}/pip 1 && \
    update-alternatives --install /usr/bin/pip3 pip3 ${PYTHON_PREFIX}/pip3 1

RUN pip install mosec

RUN mkdir -p /workspace
WORKDIR /workspace

CMD [ "/bin/bash" ]
