@echo off
mysql -u root -p < limpa.sql
python manage.py syncdb

