from django.db import models
from currencies import currencies
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
    accounting_mode = EnumField(values=('LIFO','FIFO'))
    default_currency = models.ForeignKey(Currency)

    @classmethod
    def create(cls, default_currency, accounting_mode):
        instance = cls(default_currency=currencies[default_currency], accounting_mode=accounting_mode)
        return instance

    def add_book(self, book):
        if book.profile is not None:
            raise KorovaError('Book is already in a Profile')
        book.profile = self


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

    def add_subgroup(self, group):
        if group.parent is not None:
            raise KorovaError('Subgroup already has a parent')
        group.parent = self

    def add_account(self, account):
        if account.group is not None:
            raise KorovaError('Account is already in a Group')
        account.group = self



class Account(models.Model):
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=100)
    balance = models.IntegerField()
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



    def add_pocket(self, pocket):
        if pocket.account is not None:
            raise KorovaError('Pocket is already in a Balance')

        pocket.account = self


class Pocket(models.Model):
    amount = models.IntegerField()
    source_value = models.IntegerField()
    target_value = models.IntegerField()
    date = models.DateTimeField()
    account = models.ForeignKey(Account, related_name='pockets')


class Transaction(models.Model):
    description = models.CharField(max_length=500)
    date = models.DateTimeField()

    @classmethod
    def create(cls, date, description, t_debits, t_credits):
        instance = cls(date=date, description=description)
        tot_debits = reduce(lambda x, y : x.amount + y.amount, t_debits)
        tot_credits = reduce(lambda x, y: x.amount + y.amount, t_credits)
        if tot_debits != tot_credits:
            raise KorovaError("Imbalanced Transaction")

        for split in t_debits:
            instance.add_split(split)

        for split in t_credits:
            instance.add_split(split)

    def add_split(self, split):
        if split.transaction is not None:
            raise KorovaError("Split is already in a Transaction")
        split.transaction = self


class Split(models.Model):
    amount = models.IntegerField()
    account = models.ForeignKey(Account)
    type = EnumField(values=('DEBIT','CREDIT'))
    transaction = models.ForeignKey(Transaction, related_name='splits', null=True)
