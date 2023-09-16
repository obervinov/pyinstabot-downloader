FROM python:3.10.7-alpine3.16

### External argumetns ###
ARG PROJECT_NAME
ARG PROJECT_DESCRIPTION
ARG PROJECT_VERSION

### Labels ###
LABEL org.opencontainers.image.source https://github.com/obervinov/${PROJECT_NAME}
LABEL org.opencontainers.image.description $PROJECT_DESCRIPTION
LABEL org.opencontainers.image.title "Telegram bot: pyinstabot-downloader"
LABEL org.opencontainers.image.version $PROJECT_VERSION
LABEL org.opencontainers.image.authors github.obervinov@proton.me
LABEL org.opencontainers.image.licenses https://github.com/obervinov/pyinstabot-downloader/blob/$PROJECT_VERSION/LICENSE
LABEL org.opencontainers.image.documentation https://github.com/obervinov/pyinstabot-downloader/blob/$PROJECT_VERSION/README.md
LABEL org.opencontainers.image.source https://github.com/obervinov/pyinstabot-downloader/blob/$PROJECT_VERSION

### Environment variables ###
ENV PATH=/home/${PROJECT_NAME}/.local/bin:$PATH

### Preparing user and dirs ###
RUN adduser -D -h /home/${PROJECT_NAME} -s /bin/sh ${PROJECT_NAME} && \
    mkdir -p /home/${PROJECT_NAME} && \
    mkdir -p /home/${PROJECT_NAME}/app && \
     mkdir -p /home/${PROJECT_NAME}/tmp && \
    chown ${PROJECT_NAME}. /home/${PROJECT_NAME} -R

### Prepare git
RUN apk add git

### Switching context ###
USER ${PROJECT_NAME}
WORKDIR /home/${PROJECT_NAME}/app

### Copy source code ###
COPY requirements.txt ./
COPY src/ ./

### Installing a python dependeces - requirements.txt ###
RUN pip3 install -r requirements.txt

CMD [ "python3", "bot.py" ]
