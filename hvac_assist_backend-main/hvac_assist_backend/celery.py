import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')

app = Celery('hvac_assist_backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks() 