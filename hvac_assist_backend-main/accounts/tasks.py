from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings

def build_login_url():
    # Change this to your actual login URL
    return 'http://localhost:8000/login/'

@shared_task
def send_new_user_email(email, username, password):
    subject = 'Your HVAC Assist Account Details'
    message = f"""
Hello,

Your account has been created.

Username: {username}
Password: {password}
Login here: {build_login_url()}

Please change your password after logging in.
"""
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    ) 