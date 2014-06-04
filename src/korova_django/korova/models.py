from django.db import models
from currencies import currencies
from exceptions import KorovaError
from decimal import Decimal, Context, getcontext
from django.utils import timezone

DECIMAL_ZERO = Decimal(0)
QUANTA = Decimal(10) ** (-6)

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
    accounting_mode = EnumField(values=('LIFO','FIFO'))  # for now, FIFO is assumed
    default_currency = models.ForeignKey(Currency)
    name = models.CharField(max_length=300)

    @classmethod
    def create(cls, default_currency, name, accounting_mode='FIFO'):
        return cls.objects.create(default_currency=default_currency,accounting_mode=accounting_mode, name=name)

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
        acc = Account.create(code=code, name=name, profile=self.book.profile, currency=currency, account_type=account_type)
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

    def is_foreign(self):
        return self.profile.default_currency != self.currency

    def is_local(self):
        return self.profile.default_currency == self.currency

    @classmethod
    def create(cls, code, name, profile, account_type, currency):
        instance = cls()
        instance.code=code
        instance.name=name
        instance.profile=profile
        instance.imbalance=DECIMAL_ZERO
        instance.account_type=account_type
        instance.currency=currency

        if instance.is_foreign() and ( account_type == 'INCOME' or account_type == 'EXPENSE'):
            raise KorovaError('A result account (INCOME | EXPENSE) cannot be in a foreign currency')

        instance.save()
        return instance

    # Find enough pockets to cover the requested amount, if possible
    # usage:
    #   covered_amount, pocket_info = account.find_available_pockets(amount)
    #   pocket_info is a tuple of (pocket_amount, pocket), where pocket_amount is the
    #   amount to be deduced from pocket
    def find_available_pockets(self, amount):
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

    def create_pocket(self, amount, local_amount, date):
        pkt = Pocket()
        pkt.foreign_amount = amount
        pkt.local_amount = local_amount
        pkt.foreign_balance = amount
        pkt.local_balance = local_amount
        pkt.date = date
        pkt.account = self
        pkt.save()
        return pkt

    def increase_amount(self, amount, date=timezone.now(), local_amount=None):
        if not local_amount:
            local_amount = amount

        local_amount = Decimal(local_amount).quantize(QUANTA)
        amount = Decimal(amount).quantize(QUANTA)

        if self.is_local() and local_amount != amount:
            raise KorovaError('Different amounts in local account')

        return self.create_pocket(amount, local_amount, date)

    def deduct_amount(self, amount):
        available_pockets = self.pockets.filter(foreign_balance__gt=0).order_by('date')
        amount_to_cover = Decimal(amount).quantize(QUANTA)
        local_currency_cost = DECIMAL_ZERO
        print "AVP : " + str(len(available_pockets))

        for pocket in available_pockets:

            if pocket.foreign_balance > amount_to_cover:
                #print 'X %s %s' % (unicode(pocket.foreign_amount), unicode(amount_to_cover))
                local_amount = ((pocket.local_amount*amount_to_cover)/pocket.foreign_amount).quantize(QUANTA)
                local_currency_cost += local_amount
                pocket.foreign_balance -= amount_to_cover
                pocket.local_balance -= local_amount
                if pocket.foreign_balance == DECIMAL_ZERO:
                    #print 'a ' + unicode(pocket)
                    pocket.delete()
                else:
                    #print 'b '+ unicode(pocket)
                    pocket.save()
                amount_to_cover = DECIMAL_ZERO
                break
            else:
                #print 'c '+ unicode(pocket)
                amount_to_cover -= pocket.foreign_balance
                local_currency_cost += pocket.local_balance
                #pocket.foreign_balance = DECIMAL_ZERO
                #pocket.local_balance = DECIMAL_ZERO
                #pocket.save()
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

        return  foreign_balance, local_balance


class Pocket(models.Model):
    foreign_amount = models.DecimalField(max_digits=18, decimal_places=6)   # Creation amount in the account's currency
    local_amount = models.DecimalField(max_digits=18, decimal_places=6)     # Creation amount in the profile's currency
    foreign_balance = models.DecimalField(max_digits=18, decimal_places=6)  # Current balance in the account's currency
    local_balance = models.DecimalField(max_digits=18, decimal_places=6)    # Current balance in the profile's currency
    date = models.DateTimeField()
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
    def create(cls, date, description, profile, t_debits, t_credits):
        instance = cls(date=date, description=description)
        tot_debits = reduce(lambda x, y: x.amount + y.amount, t_debits)
        tot_credits = reduce(lambda x, y: x.amount + y.amount, t_credits)
        if tot_debits != tot_credits:
            raise KorovaError("Imbalanced Transaction")

        for split in t_debits + t_credits:
            instance.add_split(split)

    def add_split(self, split):
        if split.transaction is not None:
            raise KorovaError("Split is already in a Transaction")
        split.transaction = self
        split.link()




class Split(models.Model):
    amount = models.DecimalField(max_digits=18, decimal_places=6)
    local_amount = models.DecimalField(max_digits=18,decimal_places=6)
    account = models.ForeignKey(Account, null=True)
    split_type = EnumField(values=('DEBIT', 'CREDIT'))
    is_linked = models.BooleanField()
    date = models.DateTimeField()
    transaction = models.ForeignKey(Transaction, related_name='splits', null=True)

    @classmethod
    def create(cls, amount, account, split_type, date):
        instance = Split()
        instance.amount = amount
        instance.account = account
        instance.split_type = split_type
        instance.date = date
        instance.is_linked = False
        instance.local_amount = DECIMAL_ZERO

    def link(self):
        operation = None
        local_currency_cost = DECIMAL_ZERO

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

        self.local_amount = local_currency_cost
        self.is_linked = True


class PocketOperation(models.Model):
    operation_type = EnumField(values=('CREATE', 'DECREASE'))
    pocket = models.ForeignKey(Pocket)
    split = models.ForeignKey(Split, related_name='pocketOperations')
