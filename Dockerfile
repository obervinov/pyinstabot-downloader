FROM python:3.10-alpine3.16

### External argumetns ###
ARG PROJECT_NAME

### Labels ###
LABEL org.opencontainers.image.source https://github.com/obervinov/${PROJECT_NAME}
LABEL org.opencontainers.image.description 'This project is a telegram bot that allows you to backup content from your Instagram profile to the Dropbox, Mega.io clouds or to the local filesystem.'

### Environment variables ###
ENV PATH=/home/${PROJECT_NAME}/.local/bin:$PATH

### Preparing user and dirs ###
RUN adduser -D -h /home/${PROJECT_NAME} -s /bin/sh ${PROJECT_NAME} && \
    mkdir -p /home/${PROJECT_NAME} && \
    mkdir -p /home/${PROJECT_NAME}/app && \
    chown ${PROJECT_NAME}. /home/${PROJECT_NAME}

### Switching context ###
USER ${PROJECT_NAME}
WORKDIR /home/${PROJECT_NAME}/app

### Copy source code ###
COPY requirements.txt ./
COPY src/ ./

### Installing a python dependeces - requirements.txt ###
RUN pip3 install -r requirements.txt

CMD [ "python3", "bot.py" ]
