from django.db import models
from exceptions import KorovaError
from decimal import Decimal
from django.utils import timezone
from django.core.urlresolvers import reverse
from django.db import transaction
from django.contrib.auth.models import User
from mixins import KorovaEntity


DECIMAL_ZERO = Decimal(0)
QUANTA = Decimal(10) ** (-6)


# TODO: REFACTOR THIS WHOLE THING TO USE ACCOUNT NATURE
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
            return_amount = self.account.increase_amount(split.account_amount, split.profile_amount)
        elif split.split_type == self.decrease_operation:
            return_amount = self.account.deduct_amount(split.account_amount)

        split.profile_amount = return_amount
        split.is_linked  = True
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
            return_amount = self.account.deduct_amount(split.account_amount)
        elif split.split_type == self.decrease_operation:
            return_amount = self.account.increase_amount(split.account_amount, split.profile_amount)

        split.is_linked = False
        split.profile_amount = 0
        split.save()
        return return_amount


#TODO: We need this class
class ExchangeRate(object):
    pass


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

    def __unicode__(self):
        return self.code


class Profile(models.Model):
    accounting_mode = EnumField(values=('LIFO', 'FIFO'))  # for now, FIFO is assumed
    default_currency = models.ForeignKey(Currency)
    name = models.CharField(max_length=300)
    exchange_rate_provider = None
    user = models.OneToOneField(User)

    @classmethod
    def create(cls, default_currency, name, user, accounting_mode='FIFO'):
        from currencies import XERateProvider
        instance = cls.objects.create(default_currency=default_currency,
                                      accounting_mode=accounting_mode, name=name, user=user)
        instance.set_exchange_rate_provider(XERateProvider())
        return instance

    def set_exchange_rate_provider(self, provider):
        self.exchange_rate_provider = provider

    def create_book(self, code, name, start, end=None):
        return Book.objects.create(start=start, code=code, name=name, end=end, profile=self)

    def __unicode__(self):
        return self.name


class Book(KorovaEntity):
    start = models.DateField()
    end = models.DateField(null=True)
    profile = models.ForeignKey(Profile, related_name='books')
    initial_balances_acc = models.ForeignKey('Account', null=True, blank=True, related_name='initial_balances_acc')
    profit_loss_acc = models.ForeignKey('Account', null=True, blank=True, related_name='profit_loss_acc')
    currency_xe_income_acc = models.ForeignKey('Account', null=True, blank=True, related_name='currency_xe_income_acc')
    currency_xe_expense_acc = models.ForeignKey('Account', null=True, blank=True, related_name='currency_xe_expense_acc')

    def create_top_level_group(self, name, code):
        return Group.objects.create(code=code, name=name, book=self, parent=None)

    def add_transaction(self, date, description, splits):
        if self.initial_balances_acc is None or \
                self.profit_loss_acc is None or \
                self.currency_xe_expense_acc is None or \
                self.currency_xe_income_acc is None:

            raise KorovaError("Book is not ready for transactions because one of its main accounts is null")

    def __unicode__(self):
        return "%s: (%s to %s)" % (self.profile, self.start, self.end)


class Group(KorovaEntity):
    book = models.ForeignKey(Book, related_name='groups')
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children')

    def create_child(self, name, code):
        child = Group.objects.create(code=code, name=name, book=self.book, parent=self)
        child.save()
        return child

    def create_account(self, code, name, currency, account_type):
        acc = Account.create(code=code, name=name, profile=self.book.profile,
                             currency=currency, account_type=account_type)
        acc.group = self
        acc.save()
        return acc

    def __unicode__(self):
        return "%s - %s" % (self.code, self.name)

    def get_absolute_url(self):
        return reverse('group-detail', kwargs={'pk' : self.pk})

    def __cmp__(self, other):
        return cmp(self.code, other.code)

class Account(KorovaEntity):
    imbalance = models.DecimalField(max_digits=18, decimal_places=6, default=DECIMAL_ZERO)
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

    # TODO: REFACTOR THIS LATER
    account_natures = {
        'ASSET': 'DEBIT',
        'LIABILITY': 'CREDIT',
        'INCOME': 'CREDIT',
        'EXPENSE': 'DEBIT',
        'EQUITY': 'CREDIT'
    }

    split_processor = None

    def __init__(self, *args, **kwargs):
        super(Account, self).__init__(*args, **kwargs)
        try:
            self.profile = self.group.book.profile
        except AttributeError:
            pass

    def get_nature(self):
        return self.account_natures[str(self.account_type)]

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

    def create_pocket(self, account_amount, profile_amount):
        pkt = Pocket()
        pkt.account_amount = account_amount
        pkt.profile_amount = profile_amount
        pkt.account_balance = account_amount
        pkt.profile_balance = profile_amount
        pkt.account = self
        pkt.save()
        #print 'create_procket[0] self.get_balances(): ', self.get_balances()
        return pkt.profile_amount

    def increase_amount(self, account_amount, profile_amount=None):
        #print 'increase_amount[0] ', self.name, self.account_type, account_amount, profile_amount
        if not profile_amount:
            profile_amount = account_amount

        profile_amount = Decimal(profile_amount).quantize(QUANTA)
        account_amount = Decimal(account_amount).quantize(QUANTA)
        #print 'increase_amount[1] profile_amount, account_amount:', profile_amount, account_amount

        if self.is_local() and profile_amount != account_amount:
            raise KorovaError('Different amounts in local account')

        # fix account imbalance
        inc_account_amount = max(0, account_amount - self.imbalance)

        inc_profile_amount = ((profile_amount*inc_account_amount)/account_amount).quantize(QUANTA)

        new_imbalance = max(0, self.imbalance - account_amount)
        self.imbalance = new_imbalance
        if inc_account_amount <= 0:
            return DECIMAL_ZERO

        #print 'increase_amount[2] inc_account_amount, inc_profile_amount:', inc_account_amount, inc_profile_amount
        profile_amt = self.create_pocket(inc_account_amount, inc_profile_amount)
        self.save()
        #print 'increase_amount[3] profile_amt:',profile_amt
        return profile_amt

    def deduct_amount(self, amount):
        available_pockets = self.pockets.filter(account_balance__gt=0)
        amount_to_cover = Decimal(amount).quantize(QUANTA)
        profile_currency_cost = DECIMAL_ZERO

        for pocket in available_pockets:

            if pocket.account_balance > amount_to_cover:
                profile_amount = ((pocket.profile_amount*amount_to_cover)/pocket.account_amount).quantize(QUANTA)
                profile_currency_cost += profile_amount
                pocket.account_balance -= amount_to_cover
                pocket.profile_balance -= profile_amount
                if pocket.account_balance == DECIMAL_ZERO:
                    pocket.delete()
                else:
                    pocket.save()
                amount_to_cover = DECIMAL_ZERO
                break
            else:
                amount_to_cover -= pocket.account_balance
                profile_currency_cost += pocket.profile_balance
                pocket.delete()

        if amount_to_cover > DECIMAL_ZERO:
            # could not cover all the requested amount, imbalance
            self.imbalance = amount_to_cover
            self.save()

        return profile_currency_cost

    def get_balances(self):
        my_pockets = self.pockets.filter(account_balance__gt=0)
        account_balance = DECIMAL_ZERO
        profile_balance = DECIMAL_ZERO
        for pocket in my_pockets:
            account_balance += pocket.account_balance
            profile_balance += pocket.profile_balance

        return account_balance, profile_balance

    def __unicode__(self):
        return "%s - %s" % (self.code, self.name)


class Pocket(models.Model):
    account_amount = models.DecimalField(max_digits=18, decimal_places=6)   # Creation amount in the account's currency
    profile_amount = models.DecimalField(max_digits=18, decimal_places=6)   # Creation amount in the profile's currency
    account_balance = models.DecimalField(max_digits=18, decimal_places=6)  # Current balance in the account's currency
    profile_balance = models.DecimalField(max_digits=18, decimal_places=6)  # Current balance in the profile's currency
    account = models.ForeignKey(Account, related_name='pockets')

    def __unicode__(self):
        return u'Pocket(f_amt=%s,l_amt=%s,f_bal=%s,l_bal=%s,date=%s)' % (
            self.account_amount, self.profile_amount, self.account_balance,
            self.profile_balance, self.date
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

        #print "==========================='"

        #check that no split is already in a transaction
        for s in splits:
            if s.transaction is not None:
                raise KorovaError("Split is already in a Transaction")

        t_debits = filter(lambda x: x.split_type == 'DEBIT', splits)
        t_credits = filter(lambda x: x.split_type == 'CREDIT', splits)

        foreign_increase_debit_splits = [x for x in t_debits if x.operation_sign() == 1 and
                                         x.account.is_foreign() is True]

        foreign_increase_credit_splits = [x for x in t_credits if x.operation_sign() == 1 and
                                          x.account.is_foreign() is True]

        if len(foreign_increase_credit_splits) > 1 or len(foreign_increase_debit_splits) > 1:
            raise KorovaError("Increasing the amount of more than one foreign account of same nature " +
                              " (debit/credit) is not supported")

        # assert that all increases have a profile_amount
        # first the credits:
        l_tot_credits = 0
        for split in t_credits:
            #print 'split.profile_amount =', split.profile_amount, ' split.profile_amount == DECIMAL_ZERO:', split.profile_amount == DECIMAL_ZERO, split.account.account_type
            #if split.profile_amount == DECIMAL_ZERO and split.operation_sign() == 1:  # increase
            if split.profile_amount == DECIMAL_ZERO or split.profile_amount is None:  # increase
                #print 'entrei'
                if split.account.is_foreign():
                    xchg_rate_provider = split.account.profile.exchange_rate_provider
                    xchg_rate = xchg_rate_provider.get_exchange_rate(split.account.currency,
                                                                     split.account.profile.default_currency)
                    #print xg_rate
                    split.profile_amount = xchg_rate * split.account_amount
                else:
                    split.profile_amount = split.account_amount
            l_tot_credits += split.profile_amount

        #print l_tot_credits

        # And now the debits. Locals are easy.
        l_local_debits = 0
        for split in [s for s in t_debits if s.account.is_local()]:
            l_local_debits += split.account_amount
            split.profile_amount = split.account_amount

        #print l_tot_credits, l_local_debits
        # now the foreign one, if it exists:
        try:
            foreign = foreign_increase_debit_splits[0]
            amt = l_tot_credits - l_local_debits
            if amt <= DECIMAL_ZERO:
                raise KorovaError("Nothing left to assign to foreign debit split")
            else:
                foreign.profile_amount = amt
        except IndexError:
            pass

        processed_splits = []

        # from now on, we need to rollback every processed split in case of failure
        try:
            for split in splits:
                #print 'Transaction.create 0', split.account.name, split.account.account_type, split.split_type, split.account_amount, split.profile_amount
                instance.add_split(split)
                #print 'Transaction.create 1', split.account.name, split.account.account_type, split.split_type, split.account_amount, split.profile_amount
                processed_splits.append(split)

            tot_debits = 0
            tot_credits = 0
            for x in t_debits:
                tot_debits += x.profile_amount
            for x in t_credits:
                tot_credits += x.profile_amount

            #print 'Transaction.create 2: tot_debits, tot_credits ', tot_debits, tot_credits

            if tot_credits != tot_debits:
                foreign_credit_splits = [x for x in t_credits if x.account.is_foreign() is True]
                if len(foreign_credit_splits) > 0:
                    xe_income_acc = splits[0].account.group.book.currency_xe_income_acc
                    xe_expense_acc = splits[0].account.group.book.currency_xe_expense_acc
                    #print 'xe_income_acc: ', xe_income_acc.code, xe_income_acc.name
                    #print 'xe_expense_acc: ', xe_expense_acc.code, xe_expense_acc.name
                    if tot_credits > tot_debits:
                        # We deducted from a foreign account more than we've got in a local account
                        # this is an expense
                        xcgh_split = Split.create(tot_credits - tot_debits, xe_expense_acc, 'DEBIT')
                    else:
                        xcgh_split = Split.create(tot_debits - tot_credits, xe_income_acc, 'CREDIT')
                    instance.add_split(xcgh_split)
                    processed_splits.append(xcgh_split)
                else:
                    raise KorovaError("Imbalanced Transaction")
        except KorovaError:
            for ps in processed_splits:
                ps.account.get_split_processor().unlink(ps)
            raise

        instance.save()
        # reparent all the splits and save

        for s in splits:
            s.transaction = instance
            s.save()

        return instance

    def add_split(self, split):
        split.transaction = self
        rv = split.account.get_split_processor().process(split)
        return rv


class Split(models.Model):
    account_amount = models.DecimalField(max_digits=18, decimal_places=6)
    profile_amount = models.DecimalField(max_digits=18, decimal_places=6)
    account = models.ForeignKey(Account, null=True, related_name='splits')
    split_type = EnumField(values=('DEBIT', 'CREDIT'))
    is_linked = models.BooleanField(default=False)
    transaction = models.ForeignKey(Transaction, related_name='splits', null=True)

    def __unicode__(self):
        return u"Split[acc<%s>,type<%s>,trans<%s>,acc_amt<%s>,prf_amt<%s>]" % \
            (unicode(self.account), self.split_type, unicode(self.transaction), unicode(self.account_amount),
             unicode(self.profile_amount))

    @classmethod
    def create(cls, amount, account, split_type, profile_amount=DECIMAL_ZERO):
        instance = Split()
        instance.account_amount = amount
        instance.account = account
        instance.split_type = split_type
        instance.is_linked = False
        instance.profile_amount = profile_amount
        return instance

    # this is for transaction validation purposes
    # +1 if the split will increase account balance, -1 otherwise
    def operation_sign(self):
        if self.split_type == self.account.get_nature():
            return 1
        else:
            return -1

    def save(self, *args, **kwargs):
        if self.transaction is None:
            raise KorovaError("cannot save a split without transaction")
        print 'in Split.save(): self.transaction =', self.transaction
        return super(Split, self).save(*args, **kwargs)