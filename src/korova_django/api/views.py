from django.shortcuts import render
from rest_framework import viewsets, serializers, status
from rest_framework.views import  APIView
from rest_framework.decorators import api_view
from rest_framework.response import Response
from korova.models import *
from django.db.models import get_model
from django.contrib.auth import authenticate, login, logout
from django.views.generic import View
from django.views.decorators.csrf import csrf_exempt

# Create your views here.


class BookSerializer(serializers.ModelSerializer):

    class Meta:
        model = Book
        fields = ('id', 'code', 'name', 'start', 'end')


@api_view(['POST'])
def perform_login(request):
    if request.user.is_authenticated():
        return Response({'error' : 'already logged in'})

    try:
        username = request.DATA['username']
        password = request.DATA['password']
    except KeyError:
        return Response({'error': 'username and/or password not provided', 'received': request.DATA})

    user = authenticate(username=username, password=password)
    if user is not None:
        if not user.is_active:
            return Response({'error': 'user is not active'})
    else:
        return Response({'error': 'authentication failed'})

    if user.profile is None:
        return Response({'error': 'user doesn\'t have a profile'})

    login(request, user)
    return Response({'info': 'successful authentication'})


@api_view(['POST'])
@csrf_exempt
def perform_logout(request):
    logout(request)
    return Response({'info': 'successful logout'})

@api_view(['GET'])
def get_session_book(request):
    if not request.user.is_authenticated():
        return Response(data={'error': 'not_authenticated'})

    book = Book.get_active_book(request)
    if book is None:
        return Response(data={'info': 'no book set for this session'})

    serializer = BookSerializer(book, many=False)
    return Response(serializer.data)

@api_view(['POST'])
def set_session_book(request):
    if not request.user.is_authenticated():
        return Response(data={'error': 'not_authenticated'})
    try:
        book_id = request.DATA['book_id']
    except (KeyError, ValueError):
        data = request.DATA
        return Response(data={'error': 'invalid or empty book_id passed as argument', 'received': data})
    try:
        book = Book.objects.get(pk=book_id)
    except Book.DoesNotExist:
        return Response(data={'error': 'Book id %s does not exist' % book_id})

    serializer = BookSerializer(book, many=False)
    request.session['book_id'] = book.pk

    return Response(serializer.data)


class SplitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Split

class TransactionSerializer(serializers.ModelSerializer):
    splits = SplitSerializer(source='splits', many=True)

    class Meta:
        model = Transaction



class BookViewSet(viewsets.ViewSet):
    model = Book

    def list(self, request):
        if not request.user.is_authenticated():
            return Response(data={'status': 'not_authenticated'})
        profile = request.user.profile
        books = profile.books.all()
        serializer = BookSerializer(books, many=True)
        return Response(serializer.data)



class AccountBalancesField(serializers.Field):
    def to_native(self, value):
        account = self.parent


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group

class AccountSerializer(serializers.ModelSerializer):
    group = serializers.PrimaryKeyRelatedField(source='group')
    currency = serializers.RelatedField()
    balances = serializers.Field(source='get_balances')
    group_info = serializers.Field(source='group')
    type = serializers.Field(source='account_type')
    nature = serializers.Field(source='get_nature')

    #currency = serializers.SlugRelatedField(read_only=True, slug_field='currency_name')

    class Meta:
        model = Account

        fields = ('id', 'code', 'name', 'group', 'currency', 'balances', 'group_info', 'type', 'nature')

class AccountViewSet(viewsets.ViewSet):
    model = Account

    def list(self, request):
        if not request.user.is_authenticated():
            return Response(data={'status': 'not_authenticated'})

        book = Book.get_active_book(request)

        accounts=Account.objects.filter(group__book=book).order_by('code')

        acc_serializer = AccountSerializer(accounts, many=True)
        return Response(acc_serializer.data)


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
