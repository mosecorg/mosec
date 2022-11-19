FROM python:3.11

ENV TERM xterm-256color

RUN useradd -p "" -u 1000 -s /bin/bash -m dev

RUN apt-get update && apt-get install -y git ripgrep && \
    curl --proto '=https' --tlsv1.2 -sSf https://starship.rs/install.sh | sh -s -- -y && \
    printf 'eval "$(starship init bash)"' >> /etc/bash.bashrc && \
    rm -rf /tmp/* /var/lib/apt/lists/*

USER dev

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

WORKDIR /home/dev
