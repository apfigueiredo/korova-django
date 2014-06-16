#!/usr/bin/env python

import os
os.environ['DJANGO_SETTINGS_MODULE']='main.settings'
from korova.tools import create_default_data
create_default_data()
