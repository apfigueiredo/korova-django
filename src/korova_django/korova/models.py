from django.db import models
from currencies import currencies
#import korova.currencies
from exceptions import KorovaError


# Defining class Enum
class EnumField(models.Field):
    """
    A field class that maps to MySQL's ENUM type.

    Usage:

    class Card(models.Model):
        suit = EnumField(values=('Clubs', 'Diamonds', 'Spades', 'Hearts'))

    c = Card()
    c.suit = 'Clubs'
    c.save()
    """

    def __init__(self, *args, **kwargs):
        self.values = kwargs.pop('values')
        kwargs['choices'] = [(v, v) for v in self.values]
        kwargs['default'] = self.values[0]
        super(EnumField, self).__init__(*args, **kwargs)

    def db_type(self, connection):
        return "enum({0})".format(','.join("'%s'" % v for v in self.values))


class Currency(models.Model):
    code = models.CharField(max_length=3)
    name = models.CharField(max_length=50)
    fraction = models.IntegerField()


class Profile(models.Model):
    accounting_mode = EnumField(values=('LIFO','FIFO'))  # for now, FIFO is assumed
    default_currency = models.ForeignKey(Currency)

    @classmethod
    def create(cls, default_currency, accounting_mode):
        instance = cls(default_currency=currencies[default_currency], accounting_mode=accounting_mode)
        return instance


class Book(models.Model):
    start = models.DateField()
    end = models.DateField()
    profile = models.ForeignKey(Profile, related_name='books', null=True)

    def add_group(self, group):
        if group.book is not None:
            raise KorovaError('Group is already in a Book')
        group.book = self


class Group(models.Model):
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=100)
    book = models.ForeignKey(Book, related_name='groups', null=True)
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children')


class Account(models.Model):
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=100)
    balance = models.DecimalField(max_digits=18, decimal_places=6)
    group = models.ForeignKey(Group, related_name='accounts', null=True)
    currency = models.ForeignKey(Currency)
    account_type = EnumField(values=(
                'ASSET',
                'LIABILITY',
                'INCOME',
                'EXPENSE',
                'EQUITY'
            ))

    @classmethod
    def create(cls, code, name, profile, account_type, currency):
        instance = cls(code=code, name=name, profile=profile, balance=0, account_type=account_type)
        cur_obj = currencies[currency]
        is_foreign = False
        if profile.default_currency is not cur_obj:
            is_foreign = True

        if is_foreign and ( account_type == 'INCOME' or account_type == 'EXPENSE'):
            raise KorovaError('A result account (INCOME | EXPENSE) cannot be in a foreign currency')

        return instance

    # Find enough pockets to cover the requested amount, if possible
    # usage:
    #   covered_amount, pocket_info = account.find_available_pockets(amount)
    #   pocket_info is a tuple of (pocket_amount, pocket), where pocket_amount is the
    #   amount to be deduced from pocket
    def find_available_pocket(self, amount):
        amount_to_cover = amount
        ret_pockets = []
        available_pockets = self.pockets.filter(local_balance__gt=0).order_by('date')

        for pocket in available_pockets:
            if pocket.foreign_amount >= amount_to_cover:
                ret_pockets.append((pocket, amount_to_cover))
                break
            else:
                amount_to_cover -= pocket.foreign_amount
                ret_pockets.append((pocket, pocket.foreign_amount))

        return amount_to_cover, ret_pockets

class Pocket(models.Model):
    foreign_amount = models.DecimalField(max_digits=18, decimal_places=6)   # Creation amount in the account's currency
    local_amount = models.DecimalField(max_digits=18, decimal_places=6)     # Creation amount in the profile's currency
    foreign_balance = models.DecimalField(max_digits=18, decimal_places=6)  # Current balance in the account's currency
    local_balance = models.DecimalField(max_digits=18, decimal_places=6)    # Current balance in the profile's currency
    date = models.DateTimeField()
    account = models.ForeignKey(Account, related_name='pockets')


class Transaction(models.Model):
    description = models.CharField(max_length=500)
    creation_date = models.DateTimeField()
    transaction_date = models.DateTimeField()

    @classmethod
    def _add_split_amount_to_amount_dict(cls, split, amount_dict):
        cur = split.account.currency
        try:
            amount_dict[cur] += split.amount
        except KeyError:
            amount_dict[cur] = split.amount

    @classmethod
    def _add_split_amount_to_account_dict(cls, split, account_dict):
        acc = split.account
        try:
            account_dict[acc] += split.amount
        except KeyError:
            account_dict[acc] = split.amount

    @classmethod
    def create(cls, date, description, profile, t_debits, t_credits):
        credit_amounts = {}
        debit_amounts = {}
        credit_accounts = {}
        debit_accounts = {}
        instance = cls(date=date, description=description)
        tot_debits = reduce(lambda x, y: x.amount + y.amount, t_debits)
        tot_credits = reduce(lambda x, y: x.amount + y.amount, t_credits)
        if tot_debits != tot_credits:
            raise KorovaError("Imbalanced Transaction")

        # process debits
        for split in t_debits:
            Transaction._add_split_amount_to_account_dict(split, debit_accounts)
            Transaction._add_split_amount_to_amount_dict(split, debit_amounts)
            instance.add_split(split)

        for split in t_credits:
            Transaction._add_split_amount_to_account_dict(split, credit_accounts)
            Transaction._add_split_amount_to_amount_dict(split, credit_amounts)
            instance.add_split(split)

    def add_split(self, split):
        if split.transaction is not None:
            raise KorovaError("Split is already in a Transaction")
        split.transaction = self


class PocketOperation(models.Model):
    operation_type = EnumField(values=('CREATE', 'DECREASE'))
    pocket = models.ForeignKey(Pocket)
    split = models.ForeignKey(Split, related_name='pocketOperations')


class Split(models.Model):
    amount = models.DecimalField(max_digits=18, decimal_places=6)
    account = models.ForeignKey(Account, null=True)
    split_type = EnumField(values=('DEBIT', 'CREDIT'))
    date = models.DateTimeField()
    transaction = models.ForeignKey(Transaction, related_name='splits', null=True)
    is_linked = False

    @classmethod
    def create(cls, amount, account, split_type, date):
        instance = Split()
        instance.amount = amount
        instance.account = account
        instance.split_type = split_type
        instance.date = date

    def link(self):
        operation = None
        local_currency_cost = 0

        # First, deduce if we have to increase or decrease the account balance
        if self.split_type == 'DEBIT':
            if self.account.account_type in ('ASSET', 'EXPENSE'):
                operation = 'CREATE'
            else:
                operation = 'DECREASE'
        else:
            if self.account.account_type in ('ASSET', 'EXPENSE'):
                operation = 'DECREASE'
            else:
                operation = 'CREATE'


        if operation == 'CREATE':
            po = PocketOperation()
            po.operation_type = 'CREATE'

            p = Pocket()
            p.account = self.account
            p.foreign_amount = self.amount
            p.date = self.date
            p.foreign_balance = self.amount

            po.pocket = p
            po.split = self
        else: ## 'DECREASE'
            covered_amount, pocket_info = self.account.find_available_pocket(self.amount)

            # for each element in pocket_info, we need to create a pocket operation
            for amt, pocket in pocket_info:
                pocket.foreign_balance -= amt
                local_currency_cost += (pocket.local_amount*amt)/pocket.foreign_amount
                po = PocketOperation()
                po.pocket = pocket
                po.operation_type = 'DECREASE'
                po.split = self

            # if there's any amount uncovered, we much add it to the account imbalance
            if covered_amount < self.amount:
                self.account.imbalance = self.amount - covered_amount

        return local_currency_cost
