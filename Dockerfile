FROM python:3.10.7-alpine3.16

### External argumetns ###
ARG PROJECT_NAME
ARG PROJECT_DESCRIPTION

### Labels ###
LABEL org.opencontainers.image.source https://github.com/obervinov/${PROJECT_NAME}
LABEL org.opencontainers.image.description $PROJECT_DESCRIPTION

### Environment variables ###
ENV PATH=/home/${PROJECT_NAME}/.local/bin:$PATH

### Preparing user and dirs ###
RUN adduser -D -h /home/${PROJECT_NAME} -s /bin/sh ${PROJECT_NAME} && \
    mkdir -p /home/${PROJECT_NAME} && \
    mkdir -p /home/${PROJECT_NAME}/app && \
    chown ${PROJECT_NAME}. /home/${PROJECT_NAME}

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
