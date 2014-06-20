__author__ = 'aloysio'

from django.forms import ModelForm
from korova.models import Account, Group


class AccountForm(ModelForm):
    class Meta:
        model = Account
        fields = ['group', 'currency', 'account_type']
