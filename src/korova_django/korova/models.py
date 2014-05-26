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
    type = EnumField(values=(
                'ASSET',
                'LIABILITY',
                'INCOME',
                'EXPENSE',
                'EQUITY'
            ))

    @classmethod
    def create(cls, code, name, profile, type, currency):
        instance = cls(code=code, name=name, profile=profile, balance=0, type=type)
        cur_obj = currencies[currency]
        is_foreign = False
        if profile.default_currency is not cur_obj:
            is_foreign = True

        if is_foreign and ( type == 'INCOME' or type == 'EXPENSE'):
            raise KorovaError('A result account (INCOME | EXPENSE) cannot be in a foreign currency')

        return instance

    # Find enough pockets to cover the requested amount
    def find_available_pocket(self, amount):
        available_pockets = []
        try:
            return self.pockets.filter(local_balance__gt=0).order_by('date')[0]
        except IndexError:
            return None

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


class PocketOperation(models.Model):
    type = EnumField(values=('CREATE', 'INCREASE', 'DECREASE'))
    pocket = models.ForeignKey(Pocket,related_name='pocketOperations')


class Split(models.Model):
    amount = models.DecimalField(max_digits=18, decimal_places=6)
    account = models.ForeignKey(Account)
    type = EnumField(values=('DEBIT','CREDIT'))
    date = models.DateTimeField()
    transaction = models.ForeignKey(Transaction, related_name='splits', null=True)