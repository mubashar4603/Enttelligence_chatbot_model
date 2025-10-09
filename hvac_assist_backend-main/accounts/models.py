import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('field_user', 'Field User'),
    ]
    DEPARTMENT_CHOICES = [
        ('Installation', 'Installation'),
        ('Maintenance', 'Maintenance'),
        ('Design', 'Design'),
        ('Energy Management', 'Energy Management'),
        ('Quality Control', 'Quality Control'),
        ('other', 'Other'),
    ]
    department = models.CharField(max_length=50, choices=DEPARTMENT_CHOICES, default='other')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='field_user')
