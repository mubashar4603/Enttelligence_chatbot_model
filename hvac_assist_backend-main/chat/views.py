from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Conversation, Message
from .serializers import MessageSerializer, ConversationSerializer
from .reference_loader import search_related_chunks
from rest_framework import generics, permissions
from openai import OpenAI
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from ai.agent import ai_question_answer_agent
import time

from rest_framework.permissions import IsAuthenticated

class MessageViewSet(viewsets.ModelViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    def get_queryset(self):
        queryset = Message.objects.filter(conversation__user=self.request.user)
        conversation_id = self.request.query_params.get('conversation_id')
        if conversation_id:
            queryset = queryset.filter(conversation_id=conversation_id)
        return queryset

    def query_openai(self, prompt):
        try:
            reply = ai_question_answer_agent(prompt)
        except Exception as e:
            return f"[Model API Error]: {e}", None
        # from ai.open_llm import ai_call_open_source
        # try:
        #     system_prompt = "You are an HVAC assistant. Use the following reference documents to answer the user's question."
        #     reply = ai_call_open_source(
        #         system_prompt=system_prompt,
        #         user_prompt=prompt,
        #         max_tokens=1000,
        #         temprature=0.3,
        #         model="command-r7b:latest"
        #     )
        #     # Since Ollama doesn't provide token usage, we'll set it to None
        #     token_usage = None
        #     return reply, token_usage
        # except Exception as e:
        #     return f"[Model API Error]: {e}", None



    def create(self, request, *args, **kwargs):
        t0 = time.time()
        data = request.data.copy()
        data['sender'] = 'user'
        conversation_id = data.get('conversation') or data.get('conversation_id')
        conversation = None
        new_conversation = False

        # Get or create conversation
        if conversation_id:
            try:
                conversation = Conversation.objects.get(id=conversation_id, user=request.user)
            except Conversation.DoesNotExist:
                return Response({'detail': 'Conversation not found or does not belong to user.'}, status=status.HTTP_404_NOT_FOUND)
        else:
            conversation = Conversation.objects.create(user=request.user)
            new_conversation = True

        data['conversation'] = conversation.id

        # Save user message
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        message = serializer.save()

        # Set title after saving first message
        if new_conversation:
            first_line = message.content.strip().splitlines()[0]
            title = first_line[:50].rstrip('.!?')
            conversation.title = title or "Untitled Conversation"
            conversation.save()

        relevant_text = search_related_chunks(message.content, top_k=5)
        if relevant_text.startswith('[Reference index is being built.'):
            return Response({'detail': relevant_text}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        user_message = f"Reference Documents:\n{relevant_text}\n\nUser Question: {message.content}"

        bot_reply, token_usage = self.query_openai(user_message)

        bot_message = Message.objects.create(
            conversation=conversation,
            sender='bot',
            content=bot_reply,
            token_usage=token_usage
        )

        bot_serializer = self.get_serializer(bot_message)

        t4 = time.time()
        print(f"Timing: total={t4-t0:.2f}s")

        return Response({
            'conversation_id': conversation.id,
            'message': bot_serializer.data
    }, status=status.HTTP_201_CREATED)
class UserConversationsAPIView(generics.ListAPIView):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user).order_by('-updated_at')
    

class ChatAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_message = request.data.get("message")
        if not user_message:
            return Response({"error": "Message field is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Call the open source model
            from ai.open_llm import ai_call_open_source
            # system_prompt = "You are an HVAC assistant. Help the user with their HVAC-related questions."
            bot_reply = ai_question_answer_agent(user_message)

            return Response({
                "user_message": user_message,
                "bot_reply": bot_reply
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)