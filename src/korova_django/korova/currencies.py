__author__ = 'aloysio'

from django.db.utils import ProgrammingError


currencies = {}

def initialize_currencies(sender=None, **kwargs):
    from models import Currency
    global currencies
    currencies['BRL'] = Currency.objects.get_or_create(code="BRL", name="Brazilian Real", fraction=100)[0]
    currencies['USD'] = Currency.objects.get_or_create(code="USD", name="American Dollar", fraction=100)[0]
    currencies['EUR'] = Currency.objects.get_or_create(code="EUR", name="Euro", fraction=100)[0]
    currencies['CLP'] = Currency.objects.get_or_create(code="CLP", name="Chilean Peso", fraction=1)[0]

try:
    initialize_currencies()
except ProgrammingError:
    pass