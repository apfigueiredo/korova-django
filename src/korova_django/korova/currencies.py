__author__ = 'aloysio'

from django.db.utils import ProgrammingError
from suds.client import Client
from bs4 import BeautifulSoup
from urllib2 import Request, urlopen


currencies = {}

def initialize_currencies(sender=None, **kwargs):
    from models import Currency
    global currencies
    currencies['BRL'] = Currency.objects.get_or_create(code="BRL", name="Brazilian Real", fraction=100)[0]
    currencies['USD'] = Currency.objects.get_or_create(code="USD", name="American Dollar", fraction=100)[0]
    currencies['EUR'] = Currency.objects.get_or_create(code="EUR", name="Euro", fraction=100)[0]
    currencies['CLP'] = Currency.objects.get_or_create(code="CLP", name="Chilean Peso", fraction=1)[0]

try:
    initialize_currencies()
except ProgrammingError:
    pass


class XERateProvider(object):

    # define the user agent to be used in the headers, otherwise xe.com doesn't allow us to use the service
    user_agent  = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
    user_agent += 'Ubuntu Chromium/34.0.1847.116 Chrome/34.0.1847.116 Safari/537.36'

    headers = {'User-Agent': user_agent}

    xe_url_template = 'http://www.xe.com/currencyconverter/convert/?Amount=1&From=%s&To=%s'

    def get_exchange_rate(self, rate_from, rate_to):

        headers = {'User-Agent' : self.user_agent}
        request = Request(self.xe_url_template %(rate_from, rate_to),None, headers)

        soup = BeautifulSoup(urlopen(request))

        # this is cryptic, I know... just reverse engineering on the xe HTML page
        str_rate = soup.find_all(class_='uccResUnit')[0].find_all('td')[0].text.split()[3]
        return float(str_rate)

class WSRateProvider(object):

    ws_url = 'http://www.webservicex.net/CurrencyConvertor.asmx?WSDL'

    def __init__(self):
        self.ws_client = Client(self.ws_url)

    def get_exchange_rate(self, rate_from, rate_to):
        return self.ws_client.service.ConversionRate(rate_from, rate_to)

# TODO: Rate Provider should be configurable
# For now, we will using the XE rate provider.

RateProvider = XERateProvider()
