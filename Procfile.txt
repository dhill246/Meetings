web: gunicorn -k eventlet -w 1 app:app
worker: python s3_upload_worker.py