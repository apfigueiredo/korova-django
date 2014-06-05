from django.db import models
from exceptions import KorovaError
from decimal import Decimal
from django.utils import timezone
from django.db import transaction

DECIMAL_ZERO = Decimal(0)
QUANTA = Decimal(10) ** (-6)


class SplitProcessor(object):
    def __init__(self, account, increase_operation, decrease_operation):
        self.account = account
        self.increase_operation = increase_operation
        self.decrease_operation = decrease_operation

    def process(self, split):
        if split.is_linked is True:
            raise KorovaError("Split is already processed")

        # Take a look into the future and check if there are future splits that should be reprocessed after this one
        # if so, unlink them and later process again
        future_splits = self.account.splits.filter(transaction__transaction_date__gt=split.transaction.transaction_date,
                                                   is_linked=True).order_by('transaction__transaction_date')
        return_amount = DECIMAL_ZERO
        for f_split in future_splits:
            self.unlink(f_split)

        if split.split_type == self.increase_operation:
            assert split.local_amount is not None, \
                "process: local_amount should be present for %s operation in account %s" \
                % (self.increase_operation, self.account)
            return_amount = self.account.increase_amount(split.amount, split.local_amount)
        elif split.split_type == self.decrease_operation:
            assert split.local_amount is None, \
                "process: local_amount should not be present for %s operation in account %s" \
                % (self.decrease_operation, self.account)
            return_amount = self.account.deduct_amount(split.amount)

        split.is_linked = True
        split.local_cost = return_amount
        split.save()

        # Now reprocess all the future splits:
        for f_split in future_splits:
            self.process(f_split)

        return return_amount

    def unlink(self, split):
        return_amount = DECIMAL_ZERO
        if split.account is None:
            raise KorovaError("Split is not linked to an account")
        if split.split_type == self.increase_operation:
            return_amount = self.account.deduct_amount(split.amount)
        elif split.split_type == self.decrease_operation:
            return_amount = self.account.increase_amount(split.amout, split.local_cost)

        split.is_linked = False
        split.local_cost = 0
        split.save()
        return return_amount


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
    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=50)
    fraction = models.IntegerField()

    def __cmp__(self, other):
        return cmp(self.code, other.code)


class Profile(models.Model):
    accounting_mode = EnumField(values=('LIFO', 'FIFO'))  # for now, FIFO is assumed
    default_currency = models.ForeignKey(Currency)
    name = models.CharField(max_length=300)

    @classmethod
    def create(cls, default_currency, name, accounting_mode='FIFO'):
        return cls.objects.create(default_currency=default_currency, accounting_mode=accounting_mode, name=name)

    def create_book(self, start, end=None):
        return Book.objects.create(start=start, end=end, profile=self)


class Book(models.Model):
    start = models.DateField()
    end = models.DateField(null=True)
    profile = models.ForeignKey(Profile, related_name='books')

    def create_top_level_group(self, name, code):
        return Group.objects.create(code=code, name=name, book=self, parent=None)


class Group(models.Model):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    book = models.ForeignKey(Book, related_name='groups')
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children')

    def create_child(self, name, code):
        return Group.objects.create(code=code, name=name, book=self.book, parent=self)

    def create_account(self, code, name, currency, account_type):
        acc = Account.create(code=code, name=name, profile=self.book.profile,
                             currency=currency, account_type=account_type)
        acc.group = self
        acc.save()
        return acc


class Account(models.Model):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    imbalance = models.DecimalField(max_digits=18, decimal_places=6)
    group = models.ForeignKey(Group, related_name='accounts', null=True)
    currency = models.ForeignKey(Currency)
    account_type = EnumField(values=(
        'ASSET',
        'LIABILITY',
        'INCOME',
        'EXPENSE',
        'EQUITY'
    ))

    split_processor_definitions = {
        'ASSET': ('DEBIT', 'CREDIT'),
        'LIABILITY': ('CREDIT', 'DEBIT'),
        'INCOME':  ('CREDIT', 'DEBIT'),
        'EXPENSE': ('DEBIT', 'CREDIT'),
        'EQUITY': ('CREDIT', 'DEBIT')
    }

    split_processor = None

    def get_split_processor(self):
        if self.split_processor is None:
            increase_op, decrease_op = self.split_processor_definitions[str(self.account_type)]
            self.split_processor = SplitProcessor(self, increase_op, decrease_op)

        return self.split_processor

    def is_foreign(self):
        return self.profile.default_currency != self.currency

    def is_local(self):
        return self.profile.default_currency == self.currency

    @classmethod
    def create(cls, code, name, profile, account_type, currency):
        instance = cls()
        instance.code = code
        instance.name = name
        instance.profile = profile
        instance.imbalance = DECIMAL_ZERO
        instance.account_type = account_type
        instance.currency = currency

        if instance.is_foreign() and (account_type == 'INCOME' or account_type == 'EXPENSE'):
            raise KorovaError('A result account (INCOME | EXPENSE) cannot be in a foreign currency')

        instance.save()
        return instance

    def create_pocket(self, amount, local_amount):
        pkt = Pocket()
        pkt.foreign_amount = amount
        pkt.local_amount = local_amount
        pkt.foreign_balance = amount
        pkt.local_balance = local_amount
        pkt.account = self
        pkt.save()
        return pkt.local_amount

    def increase_amount(self, amount, local_amount=None):
        if not local_amount:
            local_amount = amount

        local_amount = Decimal(local_amount).quantize(QUANTA)
        amount = Decimal(amount).quantize(QUANTA)

        if self.is_local() and local_amount != amount:
            raise KorovaError('Different amounts in local account')

        # fix account imbalance
        inc_amount = max(0, amount - self.imbalance)

        inc_local_amount = ((local_amount*inc_amount)/amount).quantize(QUANTA)

        new_imbalance = max(0, self.imbalance - amount)
        self.imbalance = new_imbalance
        if inc_amount <= 0:
            return DECIMAL_ZERO

        local_amt = self.create_pocket(inc_amount, inc_local_amount)
        self.save()
        return local_amt

    def deduct_amount(self, amount):
        available_pockets = self.pockets.filter(foreign_balance__gt=0)
        amount_to_cover = Decimal(amount).quantize(QUANTA)
        local_currency_cost = DECIMAL_ZERO

        for pocket in available_pockets:

            if pocket.foreign_balance > amount_to_cover:
                local_amount = ((pocket.local_amount*amount_to_cover)/pocket.foreign_amount).quantize(QUANTA)
                local_currency_cost += local_amount
                pocket.foreign_balance -= amount_to_cover
                pocket.local_balance -= local_amount
                if pocket.foreign_balance == DECIMAL_ZERO:
                    pocket.delete()
                else:
                    pocket.save()
                amount_to_cover = DECIMAL_ZERO
                break
            else:
                amount_to_cover -= pocket.foreign_balance
                local_currency_cost += pocket.local_balance
                pocket.delete()

        if amount_to_cover > DECIMAL_ZERO:
            # could not cover all the requested amount, imbalance
            self.imbalance = amount_to_cover
            self.save()

        return local_currency_cost

    def get_balances(self):
        my_pockets = self.pockets.filter(foreign_balance__gt=0)
        local_balance = DECIMAL_ZERO
        foreign_balance = DECIMAL_ZERO
        for pocket in my_pockets:
            local_balance += pocket.local_balance
            foreign_balance += pocket.foreign_balance

        return foreign_balance, local_balance


class Pocket(models.Model):
    foreign_amount = models.DecimalField(max_digits=18, decimal_places=6)   # Creation amount in the account's currency
    local_amount = models.DecimalField(max_digits=18, decimal_places=6)     # Creation amount in the profile's currency
    foreign_balance = models.DecimalField(max_digits=18, decimal_places=6)  # Current balance in the account's currency
    local_balance = models.DecimalField(max_digits=18, decimal_places=6)    # Current balance in the profile's currency
    account = models.ForeignKey(Account, related_name='pockets')

    def __unicode__(self):
        return u'Pocket(f_amt=%s,l_amt=%s,f_bal=%s,l_bal=%s,date=%s)' % (
            self.foreign_amount, self.local_amount, self.foreign_balance,
            self.local_balance, self.date
        )


class Transaction(models.Model):
    description = models.CharField(max_length=500)
    creation_date = models.DateTimeField()
    transaction_date = models.DateTimeField()

    @classmethod
    @transaction.atomic
    def create(cls, date, description, splits):
        instance = cls()
        instance.transaction_date = date
        instance.creation_date = timezone.now()
        instance.description = description
        t_debits = filter(lambda x: x.split_type == 'DEBIT', splits)
        t_credits = filter(lambda x: x.split_type == 'CREDIT', splits)
        tot_debits = reduce(lambda x, y: x.amount + y.amount, t_debits)
        tot_credits = reduce(lambda x, y: x.amount + y.amount, t_credits)
        if tot_debits != tot_credits:
            raise KorovaError("Imbalanced Transaction")

        for split in splits:
            instance.add_split(split)

        instance.save()
        return instance

    def add_split(self, split):
        if split.transaction is not None:
            raise KorovaError("Split is already in a Transaction")
        split.transaction = self
        split.account.get_split_processor().process(split)


class Split(models.Model):
    amount = models.DecimalField(max_digits=18, decimal_places=6)
    local_amount = models.DecimalField(max_digits=18, decimal_places=6)
    local_cost = models.DecimalField(max_digits=18, decimal_places=6)
    account = models.ForeignKey(Account, null=True, related_name='splits')
    split_type = EnumField(values=('DEBIT', 'CREDIT'))
    is_linked = models.BooleanField()
    transaction = models.ForeignKey(Transaction, related_name='splits', null=True)

    @classmethod
    def create(cls, amount, account, split_type):
        instance = Split()
        instance.amount = amount
        instance.account = account
        instance.split_type = split_type
        instance.is_linked = False
        instance.local_amount = DECIMAL_ZERO
        instance.local_cost = DECIMAL_ZERO
        return instance
