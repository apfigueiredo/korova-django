import sys
from suds.client import Client
client=Client('http://www.webservicex.net/CurrencyConvertor.asmx?WSDL')
amount = float(sys.argv[1])
from_cur = sys.argv[2]
to_cur = sys.argv[3]
rate= client.service.ConversionRate(from_cur,to_cur)
print amount*rate
