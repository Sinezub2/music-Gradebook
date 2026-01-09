from django.contrib import admin
from .models import Thread, Message


@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ("parent", "teacher", "student", "created_at")
    search_fields = ("parent__username", "teacher__username", "student__username")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("thread", "sender", "created_at")
    search_fields = ("sender__username", "text")
