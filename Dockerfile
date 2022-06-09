FROM python:3-slim

# install packages and clean up in one step
RUN apt update && apt install --yes \
    entr \
    && rm -rf /var/lib/apt/lists/*

# install python dependencies
RUN mkdir -p /app/src \
    && mkdir -p /app/config/matplotlib
WORKDIR /app
ENV MPLCONFIGDIR=/app/config/matplotlib

COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# user setup
ARG UNAME=area51
ARG UID=1051
ARG GID=1051

RUN groupadd -g ${GID} -o ${UNAME}
RUN useradd -r -u ${UID} -g ${GID} -o -s /bin/bash ${UNAME}
RUN chown -R ${UNAME}:${UNAME} /app
USER ${UNAME}

# for mac only
# ENV ENTR_INOTIFY_WORKAROUND=1

COPY entrypoint /app/
ENTRYPOINT ["/app/entrypoint"]

# prepare container for production
# COPY ./src/ /app/src/

# override for local environment
VOLUME ["/app/src"]

EXPOSE $PORT
CMD ["kickflip.py", "--budget", "250", "--go-live", "--pair", "ETHEUR"]
