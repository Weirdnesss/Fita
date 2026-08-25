from rest_framework import serializers

from .models import Chat, Message


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["id", "role", "content", "created_at"]


class ChatListSerializer(serializers.ModelSerializer):
    """For the 'Previous Chats' list -- no messages, just metadata."""

    class Meta:
        model = Chat
        fields = ["id", "title", "created_at", "updated_at"]


class ChatDetailSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Chat
        fields = ["id", "title", "messages", "created_at", "updated_at"]


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=4000)
