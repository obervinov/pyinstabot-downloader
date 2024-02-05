FROM python:3.9.15-alpine3.16

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
ENV PIP_NO_CACHE_DIR=off
ENV PIP_DISABLE_PIP_VERSION_CHECK=on
ENV POETRY_VIRTUALENVS_IN_PROJECT=true
ENV POETRY_NO_INTERACTION=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV VENV_PATH=/home/${PROJECT_NAME}/app/.venv
ENV PATH=/home/${PROJECT_NAME}/.local/bin:$VENV_PATH/bin:$PATH


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
COPY src/ src/
COPY tests/ tests/
COPY pyproject.toml .
COPY poetry.lock .
COPY *.md ./
COPY LICENSE ./

### Installing poetry and python dependeces ###
RUN curl -sSL https://install.python-poetry.org | python -
RUN poetry install
ENV PYTHONPATH=/home/${PROJECT_NAME}/app/src:/home/${PROJECT_NAME}/app/.venv/lib/python3.10/site-packages

### Entrypoint ###
CMD [ "python3", "src/bot.py" ]
