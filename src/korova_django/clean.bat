@echo off
set DJANGO_SETTINGS_MODULE=main.settings
mysql -u root -p8jkl56 < clean.sql
python manage.py syncdb --noinput
python create_default_users.py
