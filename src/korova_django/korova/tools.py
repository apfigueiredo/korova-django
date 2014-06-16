__author__ = 'aloysio'

from models import *
from currencies import currencies
from datetime import datetime


def create_default_data():
    brl = currencies['BRL']
    profile = Profile.create(brl, "Aloysio")
    book = profile.create_book(start=datetime(year=2014, month=1, day=1),
                               end=datetime(year=2014,month=6,day=1))
    ativo = book.create_top_level_group('ATIVO', '1')
    passivo = book.create_top_level_group('PASSIVO', '2')
    receita = book.create_top_level_group('RECEITA', '3')
    despesa = book.create_top_level_group('DESPESA', '4')
    pl = book.create_top_level_group('PL', '5')

    circulante = ativo.create_child('Circulante','1.01')
    itau = circulante.create_account('1.01.001', 'Conta Itau', brl, 'ASSET')

    saldos_iniciais_group = pl.create_child('Saldos Iniciais', '5.01')
    saldos_iniciais_brl = saldos_iniciais_group.create_account('Saldos Iniciais BRL','5.01.001', brl, 'EQUITY')

    fechamentos = pl.create_child('Fechamentos', '5.02')
    fechamentos_acc = fechamentos.create_account('Lucros/Despesas acumuladas','5.02.001', brl, 'EQUITY')


    receitas_genericas = receita.create_child('Genericas', '3.01')
    receita_cambio = receitas_genericas.create_account('Receitas de Cambio', '3.01.001', brl, 'INCOME')


    despesas_genericas = despesa.create_child('Genericas', '4.01')
    despesa_cambio = despesas_genericas.create_account('Despesas de Cambio', '4.01.001', brl, 'EXPENSE')


    book.currency_xe_income_acc = receita_cambio
    book.currency_xe_expense_acc = despesa_cambio
    book.initial_balances_acc = saldos_iniciais_brl
    book.profit_loss_acc = fechamentos_acc

    book.save()
