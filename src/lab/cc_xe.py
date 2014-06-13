from bs4 import BeautifulSoup as bs
import urllib2
import sys
from_cur=sys.argv[1]
to_cur = sys.argv[2]
headers={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/34.0.1847.116 Chrome/34.0.1847.116 Safari/537.36'}
req=urllib2.Request('http://www.xe.com/currencyconverter/convert/?Amount=2014&From=%s&To=%s'
% (from_cur,to_cur),None,headers)
soup=bs(urllib2.urlopen(req))
print soup.find_all(class_='uccResUnit')[0].find_all('td')[0].text.split()[3]
