from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import Conversation, Message
from .serializers import MessageSerializer, ConversationSerializer
from rest_framework import generics, permissions
from openai import OpenAI
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from django.http import StreamingHttpResponse, JsonResponse
import time
import json
from .rag_service import get_rag_service
from .intelligent_film_analytics_agent import get_intelligent_agent


class ChatAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Handle chat messages with integrated RAG and database queries"""
        user_message = request.data.get("message", "").strip()
        if not user_message:
            return Response({"error": "Message required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Initialize Intelligent Film Analytics Agent
            intelligent_agent = get_intelligent_agent()

            # Process the query with intelligent AI reasoning
            response = intelligent_agent.process_intelligent_query(user_message)

            # Return the response
            return Response({
                "message": response.get("message"),
                "type": response.get("type"),
                "data": response.get("data"),
                "sources": response.get("sources"),
                "retrieved_count": response.get("retrieved_count")
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"error": f"An error occurred: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )






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
        # For OpenAI Python SDK v1.x, use OpenAI() and set API key in env
        client = OpenAI()
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an HVAC assistant. Use the following reference documents to answer the user's question."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=256,
                temperature=0.7,
            )
            reply = response.choices[0].message.content.strip()
            token_usage = response.usage.total_tokens if response.usage else None
            return reply, token_usage
        except Exception as e:
            return f"[OpenAI API Error]: {e}", None

    def create(self, request, *args, **kwargs):
        t0 = time.time()
        from django.db import transaction
        
        with transaction.atomic():
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

        try:
            # Initialize Intelligent Film Analytics Agent
            intelligent_agent = get_intelligent_agent()

            # Process the query with intelligent AI reasoning
            query_response = intelligent_agent.process_intelligent_query(
                message.content, 
                user=request.user, 
                conversation=conversation
            )

            # Get the response message - ALWAYS natural language, no JSON
            bot_reply = query_response.get("message", "")
            
            # If there's no message but there's an error, use that instead
            if not bot_reply and query_response.get("error"):
                bot_reply = query_response.get("message", f"I'm Entelligence AI Assistant. I encountered an issue: {query_response.get('error')}")
                
            # IMPORTANT: Never include raw data/JSON in conversational responses
            # The message should already be formatted naturally by the processor
            
            # Ensure we have a valid reply
            if not bot_reply:
                bot_reply = "Hello! I'm Entelligence AI Assistant, your movie expert. I encountered an issue processing your query. Could you please rephrase your question? I'm here to help with movies, showtimes, and theaters!"

            # Create bot message
            error_response = None
            try:
                if not bot_reply:
                    raise ValueError("Empty response from query handler")
                bot_message = Message.objects.create(
                    conversation=conversation,
                    sender='bot',
                    content=bot_reply,
                    token_usage=None  # We'll need to add a field for analytics_data if we want to store the full response
                )
            except Exception as e:
                error_msg = f"An error occurred while processing your query: {str(e)}"
                # Create error message instead of failing
                bot_message = Message.objects.create(
                    conversation=conversation,
                    sender='bot',
                    content=error_msg
                )
                error_response = error_msg
        except Exception as e:
            # If we get here, something went very wrong (like DB issues)
            transaction.set_rollback(True)
            return Response(
                {"error": f"A critical error occurred: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
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

