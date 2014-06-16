from django.contrib import admin

# Register your models here.
from django.contrib import admin
from korova.models import *

admin.site.register(Profile)
admin.site.register(Book)
admin.site.register(Group)
admin.site.register(Account)
admin.site.register(Pocket)

class SplitInline(admin.TabularInline):
    model = Split
    extra = 0


class TransactionAdmin(admin.ModelAdmin):
    fieldsets = [
        (None,               {'fields': ['description']}),
        ('Date information', {'fields': ['transaction_date']}),
    ]
    inlines = [SplitInline]

admin.site.register(Transaction, TransactionAdmin)
#admin.site.register(Split)
