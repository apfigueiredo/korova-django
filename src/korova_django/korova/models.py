from django.db import models

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
    default_currency =  models.ForeignKey(Currency)


class Book(models.Model):
    start = models.DateField()
    end = models.DateField()
    profile = models.ForeignKey(Profile, related_name='books')


class Group(models.Model):
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=100)
    book = models.ForeignKey(Book, related_name='groups')
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children')


class Account(models.Model):
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=100)
    balance = models.IntegerField()
    group = models.ForeignKey(Group, related_name='accounts')
    currency = models.ForeignKey(Currency)
    type = EnumField(values=(
                'ASSET',
                'LIABILITY',
                'INCOME',
                'EXPENSE',
                'EQUITY'
            ))


class Pocket(models.Model):
    amount = models.IntegerField()
    source_value = models.IntegerField()
    target_value = models.IntegerField()
    date = models.DateTimeField()
    account = models.ForeignKey(Account, related_name='pockets')


class Transaction(models.Model):
    description = models.CharField(max_length=500)
    date = models.DateTimeField()


class Split(models.Model):
    amount = models.IntegerField()
    account = models.ForeignKey(Account)
    type = EnumField(values=('DEBIT','CREDIT'))
    transaction = models.ForeignKey(Transaction, related_name='splits')
