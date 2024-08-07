web: gunicorn -k eventlet -w 1 app:app
worker: celery -A tasks worker -P eventlet --loglevel=INFO