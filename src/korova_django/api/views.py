from django.shortcuts import render
from rest_framework import viewsets, serializers, status
from rest_framework.views import  APIView
from rest_framework.response import Response
from korova.models import *
from django.db.models import get_model

# Create your views here.


class SplitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Split


class TransactionSerializer(serializers.ModelSerializer):
    splits = SplitSerializer(source='splits', many=True)

    class Meta:
        model = Transaction


class TransactionViewSet(viewsets.ViewSet):
    model = Transaction

    def list(self, request):
        transactions = Transaction.objects.all()
        serializer = TransactionSerializer(transactions, many=True)
        return Response(serializer.data)

    def create(self, request):
        d = request.DATA
        cdate = d['creation_date']
        desc = d['description']
        splits = []
        for spl in d['splits']:
            sp = Split()
            sp.account = Account.objects.get(pk=spl['account'])
            sp.account.profile = sp.account.group.book.profile
            sp.account_amount = float(spl['account_amount'])
            sp.split_type=spl['split_type']
            try:
                sp.profile_amount = float(spl['profile_amount'])
            except KeyError:
                pass
            splits.append(sp)

        trans = Transaction.create(date=cdate,description=desc,splits=splits)
        serializer = TransactionSerializer(trans)

        return Response(data=serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self):
        return Response(status=status.HTTP_403_FORBIDDEN)
