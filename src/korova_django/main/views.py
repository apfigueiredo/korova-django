__author__ = 'aloysio'

from django.http import HttpResponse
from django.template import RequestContext, loader
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect
from django.template import RequestContext
from django.views.generic import ListView


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

@login_required(login_url='/login/')
def list_accounts(request):
    template = loader.get_template('website/list_accounts.html')
    profile = request.user.profile
    book = profile.books.all()[0]
    accounts = []
    for group in book.groups.all():
        for acc in group.accounts.all():
            accounts.append(acc)
    context = RequestContext(request, {'accounts' : accounts})
    return HttpResponse(template.render(context))



@login_required(login_url='/login/')
def perform_logout(request):
    logout(request)
    return redirect('/login')
