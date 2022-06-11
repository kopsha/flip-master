#!/usr/bin/env bash
set -e

find . | grep -E "(/__pycache__$|\.pyc$|\.pyo$)" | xargs rm -rf

user_id=$(id -u)
group_id=$(id -g)

docker build --build-arg UID=$user_id --build-arg GID=$group_id -t flip-master .

cmd=$*
docker run -ti -v $(pwd)/src:/app/src flip-master ${cmd}
