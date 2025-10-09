from django.urls import path
from .views import MessageViewSet, UserConversationsAPIView
from .views import ChatAPIView

message_list = MessageViewSet.as_view({
    'get': 'list',
    'post': 'create',
})
message_detail = MessageViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy',
})

urlpatterns = [
    path('messages/', message_list, name='message-list'),
    path('messages/<int:pk>/', message_detail, name='message-detail'),
    path('api/conversations/', UserConversationsAPIView.as_view(), name='user-conversations'),
    path("chat/", ChatAPIView.as_view(), name="chat"),
] 