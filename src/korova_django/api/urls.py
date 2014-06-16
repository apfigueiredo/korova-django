from django.conf.urls import patterns, include, url
from rest_framework_nested import routers
from api.views import *

router_transaction = routers.SimpleRouter()
router_transaction.register(r'transaction', TransactionViewSet)

urlpatterns = patterns('',
                       url(r'^', include(router_transaction.urls))
                       )