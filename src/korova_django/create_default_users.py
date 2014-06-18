__author__ = 'aloysio'


from django.db import DEFAULT_DB_ALIAS as database
from django.contrib.auth.models import User
from korova.models import Profile
from korova.currencies import currencies
brl = currencies['BRL']

User.objects.db_manager(database).create_superuser('admin', 'admin@admin.com', 'admin123')

aloysio=User.objects.create_user('aloysio','aloysio@gmail.com', 'abc123')

profile = Profile.objects.create(accounting_mode='LIFO',default_currency=brl, name="Aloysio's Profile", user=aloysio)
profile.save()