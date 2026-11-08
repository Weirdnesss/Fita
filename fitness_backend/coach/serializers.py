from rest_framework import serializers

from .models import Chat, Message, MessageRole
from .services.exercise_videos import find_exercise_videos


class MessageSerializer(serializers.ModelSerializer):
    videos = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ["id", "role", "content", "created_at", "videos"]

    def get_videos(self, obj):
        if obj.role != MessageRole.ASSISTANT:
            return []
        return find_exercise_videos(obj.content)


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