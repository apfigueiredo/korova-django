from django.test import TestCase
from korova.models import *
from korova.currencies import *
from django.utils import timezone
from django.db import IntegrityError
import random
import decimal

brl = currencies['BRL']
usd = currencies['USD']


# Create your tests here.
class KorovaModelTests(TestCase):

    @classmethod
    def setUpClass(cls):
        Profile.objects.all().delete()
        cls.profile = Profile.create(brl, "Test Profile")
        cls.book = cls.profile.create_book(start=timezone.now())
        cls.group = cls.book.create_top_level_group(name='Test Group', code='G01')

    @classmethod
    def tearDownClass(cls):
        cls.profile.delete()

    def test_duplicate_currencies(self):
        old_entries = Currency.objects.filter(code='XYZ')
        for entry in old_entries:
            entry.delete()

        with self.assertRaises(IntegrityError):
            c1 = Currency.objects.create(code='XYZ', name='Currency 1', fraction=2)
            c1.save()
            c2 = Currency.objects.create(code='XYZ', name='Currency 2', fraction=2)
            c2.save()

    def test_duplicate_accounts(self):
        old_entries = Account.objects.filter(code='XYZ')
        for entry in old_entries:
            entry.delete()

        with self.assertRaises(IntegrityError):
            self.group.create_account('XYZ', 'Account 1', brl, 'ASSET')
            self.group.create_account('XYZ', 'Account 2', brl, 'ASSET')

    def test_duplicate_groups(self):
        old_entries = Group.objects.filter(code='XYZ')
        for entry in old_entries:
            entry.delete()

        with self.assertRaises(IntegrityError):
            g1 = self.book.create_top_level_group(name='Group 1', code='XYZ')
            g2 = self.book.create_top_level_group(name='Group 2', code='XYZ')

    def test_different_amounts_in_local_account(self):
        with self.assertRaises(KorovaError):
            acc = self.group.create_account('T01', 'test account', brl, 'ASSET')
            acc.increase_amount(100, timezone.now(), 200)

    def test_equal_amounts_in_local_account(self):
        acc = self.group.create_account('T01', 'test account', brl, 'ASSET')
        acc.increase_amount(100, timezone.now(), 100)
        foreign, local = acc.get_balances()
        self.assertEqual(foreign, local)
        self.assertEqual(acc.imbalance,0)

    def test_deduct_amounts_in_local_account(self):
        acc = self.group.create_account('T01', 'test account', brl, 'ASSET')
        acc.increase_amount(1000)
        local_cost = 0
        for i in range(10):
            local_cost += acc.deduct_amount(100)

        self.assertEqual(local_cost, 1000)
        foreign, local = acc.get_balances()
        self.assertEqual(foreign, 0)
        self.assertEqual(local, 0)
        self.assertEqual(acc.imbalance,0)

    def test_deduct_amounts_in_foreign_account(self):
        acc = self.group.create_account('T01', 'test account', usd, 'ASSET')
        acc.increase_amount(1000, timezone.now(), 2000)
        local_cost = 0
        for i in range(10):
            local_cost += acc.deduct_amount(100)

        self.assertEqual(local_cost, 2000)
        foreign, local = acc.get_balances()
        self.assertEqual(foreign, 0)
        self.assertEqual(local, 0)
        self.assertEqual(acc.imbalance,0)

    def test_deduct_amount_in_foreign_account_with_multiple_pockets(self):
        acc = self.group.create_account('T01', 'test account', usd, 'ASSET')
        acc.increase_amount(1000, timezone.now(), 1000)
        acc.increase_amount(1000, timezone.now(), 2000)
        acc.increase_amount(1000, timezone.now(), 3000)
        acc.increase_amount(1000, timezone.now(), 4000)
        acc.increase_amount(1000, timezone.now(), 5000)
        local_cost = 0
        for i in range(10):
            local_cost += acc.deduct_amount(500)

        self.assertEqual(local_cost, 15000)
        foreign, local = acc.get_balances()
        self.assertEqual(foreign, 0)
        self.assertEqual(local, 0)
        self.assertEqual(acc.imbalance,0)
        self.assertFalse(acc.pockets.all())

    def test_deduct_amount_in_foreign_account_with_random_increases_and_decreases(self):
        acc = self.group.create_account('T01', 'test account', usd, 'ASSET')

        total_foreign = DECIMAL_ZERO
        for i in range(50):
            r = Decimal(random.uniform(10, 20)).quantize(QUANTA)
            #r = Decimal(random.uniform(100, 200))
            total_foreign += r
            acc.increase_amount(r, timezone.now(), Decimal(random.uniform(20,50)).quantize(QUANTA))
            #acc.increase_amount(r, timezone.now(), Decimal(random.uniform(200,500)))

        fb,dummy = acc.get_balances()
        self.assertEqual(fb, total_foreign)

        while True:
            r = Decimal(random.uniform(5, 10)).quantize(QUANTA)
            #r = Decimal(random.uniform(10, 100))
            ded = min(fb,r)
            foreign, local = acc.get_balances()
            print fb, foreign
            acc.deduct_amount(ded)
            fb -= ded

            if fb <= 0:
                break

        foreign, local = acc.get_balances()
        print fb, foreign
        self.assertEqual(foreign, 0, 'foreign = ' + unicode(foreign))
        self.assertEqual(local, 0, 'local = ' + unicode(local))
        self.assertEqual(acc.imbalance,0, 'imbalance = ' + unicode(acc.imbalance))
        self.assertFalse(acc.pockets.all())





