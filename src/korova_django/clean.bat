@echo off
mysql -u root -p8jkl56 < clean.sql
python manage.py syncdb --noinput

