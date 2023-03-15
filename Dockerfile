FROM python:3.10-alpine3.16

### External argumetns ###
ARG PROJECT_NAME

### Labels ###
LABEL org.opencontainers.image.source https://github.com/obervinov/${PROJECT_NAME}

### Environment variables ###
ENV PATH=/home/python_user/.local/bin:$PATH

### Install packages ###
RUN apk add git --no-cache

### Preparing user and dirs ###
RUN adduser -D -h /home/python_user -s /bin/sh python_user && \
    mkdir -p /home/python_user && \
    mkdir -p /var/log/${BOT_NAME} && \
    mkdir -p /home/python_user/${BOT_NAME} && \
    chown python_user. /home/python_user -R && \
    chown python_user. /var/log/${BOT_NAME}

### Switching context ###
USER python_user
WORKDIR /home/python_user/${PROJECT_NAME}

### Copy source code ###
COPY requirements.txt ./
COPY src/ ./

### Installing a python dependeces - requirements.txt ###
RUN pip3 install -r requirements.txt

CMD [ "python3", "bot.py" ]