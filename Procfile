web: bin/qgtunnel gunicorn -k eventlet -w 1 run:app
worker: celery -A app.tasks worker -P eventlet --loglevel=INFO