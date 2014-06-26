__author__ = 'aloysio'

from django.http import HttpResponse
from django.template import RequestContext, loader
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect
from django.template import RequestContext
from django.views.generic import View
from korova.exceptions import KorovaError
from .forms import AccountForm, GroupForm, TransactionForm, make_credit_split_form, make_debit_split_form
from korova.models import Group, Account, Transaction, Split
from django.forms.formsets import formset_factory
from django.forms.models import inlineformset_factory





@login_required(login_url='/login/')
def index(request):
    template = loader.get_template('website/index.html')
    user = request.user
    context = RequestContext(request, {'user' : user})
    return HttpResponse(template.render(context))

def perform_login(request):
    username = request.POST['username']
    password = request.POST['password']
    user = authenticate(username=username, password=password)
    if user is not None:
        if user.is_active:
            login(request, user)
            return redirect('/')
    else:
        return redirect('/login')


class KorovaEntityView(View):
    @classmethod
    def get_url_patterns(cls):
        from django.conf.urls import url
        urlpatterns = [
            url(r'^form/$', login_required(cls.form_view(), login_url='/login/')),
            url(r'^form/^(?P<pk>\d+)[/]?$', login_required(cls.form_view(), login_url='/login/')),
            url(r'^(?P<pk>\d+)/(?P<action>.+)', login_required(cls.as_view(), login_url='/login/')),
            url(r'^(?P<pk>\d+)[/]?$', login_required(cls.as_view(), login_url='/login/')),
            url(r'^$', login_required(cls.as_view(), login_url='/login/'))
        ]
        return urlpatterns

    def invalid_action(self, request, pk, action):
        raise KorovaError("Invalid action <%s>" % action)

    ## GET is used for the following tasks:
    ##      display a list of objects (pk=action=None)
    ##      detail an object (pk is set, action = None)
    ##      perform an action over an object (pk is set, action is set)
    def get(self, request, pk=None, action=None):
        if pk is None:
            assert (action is None)
            return self.list_objects(request)
        elif action is None:
            return self.detail_object(request, pk)
        else:
            handler = getattr(self, action.lower(), self.invalid_action)
            return handler(request, pk, action)

    ## POST is used for the following task:
    ##      adding a new object (pk=action=None)
    ##      updating an object (pk is set, action = None)
    ##      "action" is not supported for post method
    def post(self, request, pk=None, action=None):
        if action is not None:
            return self.invalid_action(request)

        if pk is None:
            return self.add_object(request)
        else:
            return self.update_object(request, pk)

    @classmethod
    def form_view(cls, **initkwargs):

        def view(request, *args, **kwargs):
            self = cls(**initkwargs)
            self.request = request
            self.args = args
            self.kwargs = kwargs
            return self.show_form(request, *args, **kwargs)
        return view


class AccountView(KorovaEntityView):
    list_template = loader.get_template('website/account/list.html')
    form_template = loader.get_template('website/account/form.html')

    def build_group_tree(self, group, html_result=""):
        original = html_result
        html_result += "<li>%s - %s" % (group.code, group.name)
        for subgroup in group.children.all():
            html_result += "<ul>" + self.build_group_tree(subgroup, original) + "</ul>"
        accounts_html = ""
        for account in group.accounts.all():
            accounts_html += "<li>%s - %s - %s %s    <a href=\"/account/%d/delete_object\">delete</a></li>" % \
                             (account.code, account.name, account.get_balances()[0], account.currency.code, account.pk)
        if accounts_html:
            html_result += "<ul>" + accounts_html + "</ul>"
        html_result += "</li>"
        return html_result

    def delete_object(self, request, pk, action):
        account = Account.objects.get(pk=pk)
        account.delete()
        return redirect('/account')

    def add_object(self, request):
        form = AccountForm(request.POST)
        new_account = form.save()
        return redirect('/account')

    def show_form(self, request, pk=None):
        profile = request.user.profile
        form = AccountForm()
        form.fields['group'].queryset = Group.objects.filter(book=profile.books.all()[0]).order_by('code')
        context = RequestContext(request, {'form' : form})
        return HttpResponse(self.form_template.render(context))

    def list_objects(self, request):
        profile = request.user.profile
        book = profile.books.all()[0]
        book_html = "<ul>"
        for group in book.groups.filter(parent=None):
            book_html += self.build_group_tree(group)
        book_html += "</ul>"
        context = RequestContext(request, {'book_html' : book_html})
        return HttpResponse(self.list_template.render(context))


class GroupView(KorovaEntityView):
    list_template = loader.get_template('website/group/list.html')
    form_template = loader.get_template('website/group/form.html')

    def build_group_tree(self, group, html_result=""):
        original = html_result
        html_result += "<li>%s - %s - - <a href=\"/account/%d/delete_object\">delete</a>" % (group.code, group.name,
                                                                                             group.pk)
        for subgroup in group.children.all():
            html_result += "<ul>" + self.build_group_tree(subgroup, original) + "</ul>"
        return html_result

    def add_object(self, request):
        form = GroupForm(request.POST)
        print 'is_valid: ' + str(form.is_valid())
        new_group = Group(**form.cleaned_data)
        profile = request.user.profile
        new_group.book = profile.books.all()[0]
        new_group.save()
        return redirect('/group')

    def show_form(self, request, pk=None):
        profile = request.user.profile
        form = GroupForm()
        form.fields['parent'].queryset = Group.objects.filter(book=profile.books.all()[0]).order_by('code')
        context = RequestContext(request, {'form' : form})
        return HttpResponse(self.form_template.render(context))

    def delete_object(self, request, pk, action):
        group = Group.objects.get(pk=pk)
        group.delete()
        return redirect('/group')

    def list_objects(self, request):
        profile = request.user.profile
        book = profile.books.all()[0]
        book_html = "<ul>"
        for group in book.groups.filter(parent=None):
            book_html += self.build_group_tree(group)
        book_html += "</ul>"
        context = RequestContext(request, {'book_html' : book_html})
        return HttpResponse(self.list_template.render(context))


class TransactionView(KorovaEntityView):
    list_template = loader.get_template("website/transaction/list.html")
    form_template = loader.get_template("website/transaction/form.html")

    def list_objects(self, request):
        context = RequestContext(request, {})
        return HttpResponse(self.list_template.render(context))

    def add_object(self, request):
        profile = request.user.profile
        book = profile.books.all()[0]
        _CreditFormSet = inlineformset_factory(Transaction, Split,
                                               form=make_credit_split_form(book),
                                               can_delete=False,
                                               extra=6)
        _DebitFormSet = inlineformset_factory(Transaction, Split,
                                              form=make_debit_split_form(book),
                                              can_delete=False,
                                              extra=6)
        transaction_form = TransactionForm(request.POST)
        credit_formset = _CreditFormSet(request.POST, request.FILES, prefix='credit')
        debit_formset = _CreditFormSet(request.POST, request.FILES, prefix='debit')

        splits = []
        date = transaction_form.data['transaction_date'] + ' 00:00'
        description = transaction_form.data['description']

        if not credit_formset.is_valid():
            print credit_formset.errors

        if not debit_formset.is_valid():
            print debit_formset.errors

        for form in credit_formset:
            #s = Split.create(form.data['account_amount'], form.data['account'],
            #                 form.data['split_type'], form.data['profile_amount'])
            split = Split(**form.cleaned_data)
            if split.account is None or split.account_amount is None:
                continue
            print split
            split.transaction = None
            splits.append(split)

        for form in debit_formset:
            #s = Split.create(form.data['account_amount'], form.data['account'],
            #                 form.data['split_type'], form.data['profile_amount'])
            split = Split(**form.cleaned_data)
            if split.account is None or split.account_amount is None:
                continue

            print split
            split.transaction = None
            splits.append(split)

        new_transaction = Transaction.create(date, description, splits)

        return redirect('/transaction')

    def show_form(self, request, pk=None):
        profile = request.user.profile
        book = profile.books.all()[0]
        transaction_form = TransactionForm()
        _CreditFormSet = inlineformset_factory(Transaction, Split,
                                               form=make_credit_split_form(book),
                                               can_delete=False,
                                               extra=6)
        _DebitFormSet = inlineformset_factory(Transaction, Split,
                                              form=make_debit_split_form(book),
                                              can_delete=False,
                                              extra=6)
        credit_formset = _CreditFormSet(prefix='credit')
        debit_formset = _DebitFormSet(prefix='debit')
        context = RequestContext(request, {'transaction_form': transaction_form,
                                           'credit_formset': credit_formset,
                                           'debit_formset': debit_formset})
        return HttpResponse(self.form_template.render(context))


@login_required(login_url='/login/')
def perform_logout(request):
    logout(request)
    return redirect('/login')
