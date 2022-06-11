#!/usr/bin/env bash
set -e

PROJECT_ROOT=$(git rev-parse --show-toplevel)
PROJECT_NAME=$(basename $PROJECT_ROOT)

printf " --\n"
printf " -- stopping previous version\n"
printf " --\n"
ssh fibonet /bin/bash <<'EOT'
set -e
cd /var/www/penny
docker-compose down --remove-orphans
EOT

printf " --\n"
printf " -- deploying $PROJECT_NAME (from $PROJECT_ROOT)\n"
printf " --\n"

cd $PROJECT_ROOT
find . | grep -E "(/__pycache__$|\.pyc$|\.pyo$)" | xargs rm -rf

printf "copying files"
rsync -az $PROJECT_ROOT/ fibonet:/var/www/penny/

## update permissions
ssh fibonet chown caddy:caddy /var/www/penny
ssh fibonet chmod o+t /var/www/penny
ssh fibonet chmod a+rwx /var/www/penny

ssh fibonet chown -R area51:area51 /var/www/penny

## service recomposition
printf " --\n"
printf " -- rebuilding services\n"
printf " --\n"

ssh fibonet /bin/bash <<'EOT'
set -e
cd /var/www/penny
docker-compose up -d --build --remove-orphans
EOT

printf " -- done\n"
