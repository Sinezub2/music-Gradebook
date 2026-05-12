#!/bin/sh
set -eu

if [ "${DJANGO_COLLECTSTATIC:-1}" = "1" ]; then
  python manage.py collectstatic --noinput
fi

if [ "${DJANGO_MIGRATE:-1}" = "1" ]; then
  python manage.py migrate --noinput
fi

if [ "${DJANGO_SEED_DEMO:-0}" = "1" ]; then
  python manage.py seed_demo
fi

set -- python manage.py runserver 0.0.0.0:8000

if [ "${DJANGO_LIVE_STATIC:-0}" = "1" ]; then
  set -- "$@" --insecure
fi

exec "$@"
