__author__ = 'aloysio'

from django.http import HttpResponse
from django.template import RequestContext, loader
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect
from django.template import RequestContext
from django.views.generic import View
from korova.exceptions import KorovaError
from .forms import AccountForm
from korova.models import Group





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
            #url(r'^(?P<pk>\d+)/(?P<action>.+)', login_required(cls.as_view(), login_url='/login/')),
            #url(r'^(?P<pk>\d+)[/]?$', login_required(cls.as_view(), login_url='/login/')),
            #url(r'^', login_required(cls.as_view(), login_url='/login/'))
        ]
        return urlpatterns

    def invalid_action(self, request):
        raise KorovaError("Invalid action <%s>")

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
            return handler(request, pk)

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
            accounts_html += "<li>%s - %s</li>" % (account.code, account.name)
        if accounts_html:
            html_result += "<ul>" + accounts_html + "</ul>"
        html_result += "</li>"
        return html_result

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
    list_template = loader.get_template('website/account/list.html')

    def build_group_tree(self, group):
        group.has_children = False
        for subgroup in group.children.all():
            self.build_group_tree(subgroup)

    def list_objects(self, request):
        pass


@login_required(login_url='/login/')
def perform_logout(request):
    logout(request)
    return redirect('/login')
