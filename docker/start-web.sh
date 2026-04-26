#!/bin/sh
set -eu

python manage.py collectstatic --noinput
python manage.py migrate --noinput

if [ "${DJANGO_SEED_DEMO:-0}" = "1" ]; then
  python manage.py seed_demo
fi

exec python manage.py runserver 0.0.0.0:8000
