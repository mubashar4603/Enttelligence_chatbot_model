from django.contrib import admin
from .models import Conversation, Message, Document

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'title', 'created_at', 'updated_at')
    search_fields = ('title', 'user__username')
    list_filter = ('created_at', 'updated_at')

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'sender', 'created_at', 'token_usage')
    search_fields = ('content',)
    list_filter = ('sender', 'created_at')

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'message', 'file', 'uploaded_at')
    search_fields = ('file', 'extracted_text')
    list_filter = ('uploaded_at',)
