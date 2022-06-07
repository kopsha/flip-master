#!/usr/bin/env bash
set -e

user_id=$(id -u)
group_id=$(id -g)

docker build --build-arg UID=$user_id --build-arg GID=$group_id -t flip-master .

if [[ $# -eq 0 ]];
then
    cmd=develop
else
    cmd=$*
fi

USE_PORT=6765
docker run -ti -v $(pwd)/src:/app/src -e PORT=$USE_PORT -p $USE_PORT:$USE_PORT flip-master ${cmd}
