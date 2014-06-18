from django.db import models


class KorovaEntity(models.Model):

    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=200)

    class Meta:
        abstract = True
