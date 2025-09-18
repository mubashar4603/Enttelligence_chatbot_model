import random
import string


def generate_temp_password(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))