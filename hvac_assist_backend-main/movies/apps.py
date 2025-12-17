from django.apps import AppConfig
import os

class MoviesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'movies'
    path = os.path.dirname(os.path.abspath(__file__))
