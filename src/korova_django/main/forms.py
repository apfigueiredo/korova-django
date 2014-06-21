__author__ = 'aloysio'

from django.forms import ModelForm
from django import forms
from korova.models import Account, Group, Transaction, Split


class AccountForm(ModelForm):
    class Meta:
        model = Account
        fields = ['code', 'name', 'group', 'currency', 'account_type']


class GroupForm(ModelForm):
    class Meta:
        model = Group
        fields = ['code', 'name', 'parent']


class TransactionForm(ModelForm):
    transaction_date = forms.DateField(widget=forms.TextInput(attrs={'class': 'datepicker'}))

    class Meta:
        model = Transaction
        fields = ['description', 'transaction_date']


class SplitForm(ModelForm):
    class Meta:
        model = Split
        fields = ['account', 'account_amount', 'profile_amount', 'split_type']


def make_credit_split_form(book):
    class CreditSplitForm(SplitForm):
        split_type = forms.CharField(widget=forms.HiddenInput(), initial='CREDIT')
        #account = forms.ModelChoiceField(
        #    queryset=Account.objects.filter(
        #        Q(account_type='LIABILITY') | Q(account_type='INCOME') | Q(account_type='EQUITY'),
        #        group__book=book))
        account = forms.ModelChoiceField(
            queryset=Account.objects.filter(group__book=book).order_by('code'))
    return CreditSplitForm


def make_debit_split_form(book):
    class DebitSplitForm(SplitForm):
        split_type = forms.CharField(widget=forms.HiddenInput(), initial='DEBIT')
        #account = forms.ModelChoiceField(
        #    queryset=Account.objects.filter(
        #        Q(account_type='ASSET') | Q(account_type='EXPENSE'),
        #        group__book=book))
        account = forms.ModelChoiceField(
            queryset=Account.objects.filter(group__book=book).order_by('code'))
    return DebitSplitForm


