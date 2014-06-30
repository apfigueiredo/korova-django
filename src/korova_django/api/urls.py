from django.conf.urls import patterns, include, url
from rest_framework_nested import routers
from api.views import *

router_transaction = routers.SimpleRouter()
router_transaction.register(r'transaction', TransactionViewSet)

router_accounts = routers.SimpleRouter()
router_accounts.register(r'accounts', AccountViewSet)

router_books = routers.SimpleRouter()
router_books.register(r'books', BookViewSet)

urlpatterns = patterns('',
                       url(r'^get_session_book/', 'api.views.get_session_book', name='get_session_book'),
                       url(r'^set_session_book/', 'api.views.set_session_book', name='set_session_book'),
                       url(r'^perform_login/', 'api.views.perform_login', name='perform_login'),
                       url(r'^perform_logout/', 'api.views.perform_logout', name='perform_logout'),
                       url(r'^', include(router_transaction.urls)),
                       url(r'^', include(router_accounts.urls)),
                       url(r'^', include(router_books.urls))
                       )