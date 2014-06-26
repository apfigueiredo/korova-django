__author__ = 'aloysio'

from models import *
from currencies import currencies
from datetime import datetime
from django.contrib.auth.models import User
import sys
import os


def create_default_data():
    brl = currencies['BRL']
    usd = currencies['USD']
    eur = currencies['EUR']
    account_types = {'1': 'ASSET',
                     '2': 'LIABILITY',
                     '3': 'INCOME',
                     '4': 'EXPENSE',
                     '5': 'EQUITY'}

    groups = {}
    accounts = {}

    user = User.objects.get(username="aloysio")
    profile = user.profile
    book = profile.create_book(start=datetime(year=2014, month=1, day=1),
                               end=datetime(year=2014,month=6,day=1),
                               code='201401',
                               name='Primeiro Semestre de 2014')

    input_file = file(os.path.dirname(sys.modules[__name__].__file__) + '/accounts.txt')
    for line in input_file.readlines():
        code, name = [value.strip() for value in line.split('|')]
        if len(code) == 1:  # it is a top level group
            groups[code] = book.create_top_level_group(name, code)
        elif len(code) == 4:  # it is a subgroup
            parent_code = code.split('.')[0]
            parent = groups[parent_code]
            groups[code] = parent.create_child(name, code)
        else:  # it is an account
            parent_group_code = '.'.join(code.split('.')[:-1])
            parent_group = groups[parent_group_code]
            account_type = account_types[parent_group_code[0]]
            accounts[code] = parent_group.create_account(code, name, brl, account_type)

    # handle special cases
    accounts['1.03.001'].currency = usd
    accounts['1.03.001'].save()
    accounts['1.03.002'].currency = eur
    accounts['1.03.002'].save()

    book.currency_xe_income_acc = accounts['3.02.008']
    book.currency_xe_expense_acc = accounts['4.08.003']
    book.initial_balances_acc = accounts['5.01.001']
    book.profit_loss_acc = accounts['5.01.002']

    book.save()
