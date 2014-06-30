from django.conf.urls import patterns, include, url
from django.views.generic import TemplateView
from views import AccountView, GroupView, TransactionView, IndexView
from django.contrib.auth.decorators import login_required

from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    url(r'^login/', TemplateView.as_view(template_name='website/login.html')),
    url(r'^perform_login/', 'main.views.perform_login', name='perform_login'),
    url(r'^perform_logout/', 'main.views.perform_logout', name='perform_logout'),

    url(r'^$', login_required(IndexView.as_view()), name='index'),
    url(r'^account/', include(AccountView.get_url_patterns())),
    url(r'^group/', include(GroupView.get_url_patterns())),
    url(r'^transaction/', include(TransactionView.get_url_patterns())),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^api/', include('api.urls'))
)
