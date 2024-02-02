FROM python:3.10.7-alpine3.16

### External argumetns ###
ARG PROJECT_DESCRIPTION
ARG PROJECT_NAME
ARG PROJECT_VERSION

### Labels ###
LABEL org.opencontainers.image.source https://github.com/obervinov/${PROJECT_NAME}
LABEL org.opencontainers.image.description ${PROJECT_DESCRIPTION}
LABEL org.opencontainers.image.version ${PROJECT_VERSION}
LABEL org.opencontainers.image.authors github.obervinov@proton.me
LABEL org.opencontainers.image.licenses https://github.com/obervinov/${PROJECT_NAME}/blob/${PROJECT_VERSION}/LICENSE
LABEL org.opencontainers.image.documentation https://github.com/obervinov/${PROJECT_NAME}/blob/${PROJECT_VERSION}/README.md
LABEL org.opencontainers.image.source https://github.com/obervinov/${PROJECT_NAME}/blob/${PROJECT_VERSION}

### Environment variables ###
ENV PATH=/home/${PROJECT_NAME}/.local/bin:/root/.local/bin:$PATH
ENV PIP_NO_CACHE_DIR=off
ENV PIP_DISABLE_PIP_VERSION_CHECK=on
ENV POETRY_VIRTUALENVS_IN_PROJECT=false
ENV POETRY_NO_INTERACTION=1

### Preparing user and directories ###
RUN adduser -D -h /home/${PROJECT_NAME} -s /bin/sh ${PROJECT_NAME} && \
    mkdir -p /home/${PROJECT_NAME} && \
    mkdir -p /home/${PROJECT_NAME}/app && \
    mkdir -p /home/${PROJECT_NAME}/tmp && \
    chown ${PROJECT_NAME}. /home/${PROJECT_NAME} -R

### Prepare tools and fix vulnerabilities ###
RUN apk upgrade --no-cache && apk add --no-cache git curl

### Switching context ###
USER ${PROJECT_NAME}
WORKDIR /home/${PROJECT_NAME}/app

### Copy source code ###
COPY poetry.lock pyproject.toml ./
COPY src/ ./

### Installing poetry and python dependeces ###
RUN curl -sSL https://install.python-poetry.org | python -
RUN poetry install --no-root

### Entrypoint ###
CMD [ "python3", "bot.py" ]
