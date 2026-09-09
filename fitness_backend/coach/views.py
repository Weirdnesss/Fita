import logging

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Chat, Message, MessageRole
from .serializers import (
    ChatDetailSerializer,
    ChatListSerializer,
    SendMessageSerializer,
)
from .services.llm_service import LLMService

logger = logging.getLogger(__name__)


class ChatListCreateView(generics.ListCreateAPIView):
    """
    GET  /coach/chats/   -- "Previous Chats" list
    POST /coach/chats/   -- "+ New Chat" button, body optional {"title": "..."}
    """

    serializer_class = ChatListSerializer

    def get_queryset(self):
        return Chat.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ChatDetailView(generics.RetrieveDestroyAPIView):
    """GET/DELETE /coach/chats/<id>/  -- open a chat, or delete it."""

    serializer_class = ChatDetailSerializer

    def get_queryset(self):
        return Chat.objects.filter(user=self.request.user)


class SendMessageView(APIView):
    """
    POST /coach/chats/<id>/messages/
    Body: {"content": "Give me a workout routine"}
    Saves the user message, calls the LLM with full context, saves and
    returns the assistant's reply.
    """

    def post(self, request, chat_id):
        chat = get_object_or_404(Chat, id=chat_id, user=request.user)

        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_content = serializer.validated_data["content"]

        Message.objects.create(chat=chat, role=MessageRole.USER, content=user_content)

        # First message in a fresh chat becomes the chat's title.
        if chat.title == "New Chat":
            chat.title = user_content[:60]
            chat.save(update_fields=["title"])

        try:
            llm_service = LLMService()
            reply_text = llm_service.get_response(chat)
        except Exception:
            # Full detail (which can include config errors like a
            # missing GROQ_API_KEY, or raw SDK/network exceptions) goes
            # to the server log only -- never back to the client.
            logger.exception("LLM service call failed for chat %s", chat_id)
            return Response(
                {"error": "Assistant is unavailable right now. Please try again shortly."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        assistant_message = Message.objects.create(
            chat=chat, role=MessageRole.ASSISTANT, content=reply_text
        )
        chat.save(update_fields=["updated_at"])

        return Response(
            {
                "user_message": user_content,
                "assistant_message": assistant_message.content,
                "message_id": assistant_message.id,
            },
            status=status.HTTP_201_CREATED,
        )