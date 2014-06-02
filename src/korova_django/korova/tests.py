from django.test import TestCase
from korova.models import *
from korova.currencies import *
from datetime import datetime

brl = currencies['BRL']


# Create your tests here.
class KorovaModelTests(TestCase):

    def test_create_profile(self):
        p = Profile.create(brl,'FIFO')
        id = p.pk
        del(p)
        p = Profile.objects.get(pk=id)
        self.assertEqual(p.default_currency, brl)
        self.assertEqual(p.accounting_mode, 'FIFO')

    def test_create_book(self):
        p = Profile.create(brl, 'FIFO')
        p.create_book(start=datetime.now())
        self.assertTrue(p.books)

    def test_create_top_level_group(self):
        p = Profile.create(brl)
        book = p.create_book(start=datetime.now())
        book.create_top_level_group(name='Assets', code='1')
        self.assertTrue(book.groups)

    def test_create_subgroup(self):
        p = Profile.create(brl)
        book = p.create_book(start=datetime.now())
        top_level = book.create_top_level_group(name='Assets', code='1')
        top_level.create_child(name='Current', code='1.1')
        self.assertTrue(top_level.children)

    def test_create_account(self):
        p = Profile.create(brl)
        book = p.create_book(start=datetime.now())
        top_level = book.create_top_level_group(name='Assets', code='1')
        top_level.create_account('1.1.01', 'Conta Bradesco', brl, 'ASSET')
        self.assertTrue(top_level.accounts)

