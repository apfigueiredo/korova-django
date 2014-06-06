from django.test import TestCase
from korova.models import *
from korova.currencies import *
from django.utils import timezone
from django.db import IntegrityError
import random

brl = currencies['BRL']
usd = currencies['USD']


# Create your tests here.
class KorovaModelTests(TestCase):

    profile = None

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
            self.book.create_top_level_group(name='Group 1', code='XYZ')
            self.book.create_top_level_group(name='Group 2', code='XYZ')

    def test_different_amounts_in_local_account(self):
        with self.assertRaises(KorovaError):
            acc = self.group.create_account('T01', 'test account', brl, 'ASSET')
            acc.increase_amount(100, 200)

    def test_equal_amounts_in_local_account(self):
        acc = self.group.create_account('T01', 'test account', brl, 'ASSET')
        acc.increase_amount(100, 100)
        foreign, local = acc.get_balances()
        self.assertEqual(foreign, local)
        self.assertEqual(acc.imbalance, 0)

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
        self.assertEqual(acc.imbalance, 0)

    def test_deduct_amounts_in_foreign_account(self):
        acc = self.group.create_account('T01', 'test account', usd, 'ASSET')
        acc.increase_amount(1000, 2000)
        local_cost = 0
        for i in range(10):
            local_cost += acc.deduct_amount(100)

        self.assertEqual(local_cost, 2000)
        foreign, local = acc.get_balances()
        self.assertEqual(foreign, 0)
        self.assertEqual(local, 0)
        self.assertEqual(acc.imbalance, 0)

    def test_deduct_amount_in_foreign_account_with_multiple_pockets(self):
        acc = self.group.create_account('T01', 'test account', usd, 'ASSET')
        acc.increase_amount(1000, 1000)
        acc.increase_amount(1000, 2000)
        acc.increase_amount(1000, 3000)
        acc.increase_amount(1000, 4000)
        acc.increase_amount(1000, 5000)
        local_cost = 0
        for i in range(10):
            local_cost += acc.deduct_amount(500)

        self.assertEqual(local_cost, 15000)
        foreign, local = acc.get_balances()
        self.assertEqual(foreign, 0)
        self.assertEqual(local, 0)
        self.assertEqual(acc.imbalance, 0)
        self.assertFalse(acc.pockets.all())

    def test_deduct_amount_in_foreign_account_with_random_increases_and_decreases(self):
        acc = self.group.create_account('T01', 'test account', usd, 'ASSET')

        total_profile_amount = DECIMAL_ZERO
        for i in range(50):
            r = Decimal(random.uniform(10, 20)).quantize(QUANTA)
            total_profile_amount += r
            acc.increase_amount(r, Decimal(random.uniform(20, 50)).quantize(QUANTA))

        account_balance, dummy = acc.get_balances()
        self.assertEqual(account_balance, total_profile_amount)

        while True:
            r = Decimal(random.uniform(5, 10)).quantize(QUANTA)
            ded = min(account_balance, r)
            acc.deduct_amount(ded)
            account_balance -= ded
            if account_balance <= 0:
                break

        account_amount, profile_amount = acc.get_balances()
        self.assertEqual(account_amount, 0, 'foreign = ' + unicode(account_amount))
        self.assertEqual(profile_amount, 0, 'local = ' + unicode(profile_amount))
        self.assertEqual(acc.imbalance, 0, 'imbalance = ' + unicode(acc.imbalance))
        self.assertFalse(acc.pockets.all())

    def test_recover_imbalance_with_residual_imbalance(self):
        acc = self.group.create_account('T01', 'test account', usd, 'ASSET')
        acc.deduct_amount(100)
        acc.increase_amount(50, 100)
        account_amount, profile_amount = acc.get_balances()
        self.assertEqual(account_amount, 0)
        self.assertEqual(profile_amount, 0)
        self.assertEqual(acc.imbalance, 50)

    def test_recover_imbalance_full_no_residuals(self):
        acc = self.group.create_account('T01', 'test account', usd, 'ASSET')
        acc.deduct_amount(100)
        acc.increase_amount(100, 200)
        account_amount, profile_amount = acc.get_balances()
        self.assertEqual(account_amount, 0)
        self.assertEqual(profile_amount, 0)
        self.assertEqual(acc.imbalance, 0)

    def test_recover_imbalance_with_residual_balance(self):
        acc = self.group.create_account('T01', 'test account', usd, 'ASSET')
        acc.deduct_amount(100)
        acc.increase_amount(200, 400)
        account_balance, profile_balance = acc.get_balances()

        self.assertEqual(account_balance, 100)
        self.assertEqual(acc.imbalance, 0)
        self.assertEqual(profile_balance, 200)

    def test_transaction_local_accounts_asset_liability(self):
        asset = self.group.create_account('T01', 'test account', brl, 'ASSET')
        liability = self.group.create_account('T02', 'test account', brl, 'LIABILITY')

        split_liability = Split.create(100, liability, 'CREDIT')
        split_asset = Split.create(100, asset, 'DEBIT')

        Transaction.create(timezone.now(), "Test Transaction", [split_liability, split_asset])
        aab, apb = asset.get_balances()
        lab, lpb = liability.get_balances()
        self.assertEqual(aab, 100)
        self.assertEqual(apb, 100)
        self.assertEqual(lab, 100)
        self.assertEqual(lpb, 100)
