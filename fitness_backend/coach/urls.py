from django.urls import path

from .views import ChatDetailView, ChatListCreateView, SendMessageView

urlpatterns = [
    path("chats/", ChatListCreateView.as_view(), name="chat-list"),
    path("chats/<int:pk>/", ChatDetailView.as_view(), name="chat-detail"),
    path("chats/<int:chat_id>/messages/", SendMessageView.as_view(), name="send-message"),
]
