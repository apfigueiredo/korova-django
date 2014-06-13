import sys
from suds.client import Client
client=Client('http://www.webservicex.net/CurrencyConvertor.asmx?WSDL')
from_cur = sys.argv[1]
to_cur = sys.argv[2]
rate= client.service.ConversionRate(from_cur,to_cur)
print rate
