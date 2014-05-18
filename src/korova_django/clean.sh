#!/bin/bash
mysql -u root -p < clean.sql
python manage.py syncdb

