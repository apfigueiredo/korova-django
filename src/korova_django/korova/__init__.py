from django.db.models.signals import post_syncdb
from korova.currencies import initialize_currencies
import models

post_syncdb.connect(initialize_currencies, sender=models)

