from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.db.models import OuterRef, Subquery, F, ExpressionWrapper, DurationField, Avg
from django.db import models
from datetime import timedelta

from chat.models import Message, Feedback
from accounts.models import CustomUser

from rest_framework import generics
from rest_framework.permissions import IsAdminUser
from django.db.models import Count, Max
from accounts.models import CustomUser
from .serializers import UserManagementSerializer

class AdminDashboardOverviewAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        total_users = CustomUser.objects.count()
        total_queries = Message.objects.filter(sender='user').count()

        # Subquery to get the timestamp of the first bot reply after each user message
        bot_reply_subquery = Message.objects.filter(
            conversation=OuterRef('conversation'),
            sender='bot',
            created_at__gt=OuterRef('created_at')
        ).order_by('created_at').values('created_at')[:1]

        # Annotate user messages with bot reply time and calculate response time
        user_messages = Message.objects.filter(sender='user').annotate(
            bot_reply_time=Subquery(bot_reply_subquery)
        ).exclude(bot_reply_time=None).annotate(
            response_time=ExpressionWrapper(
                F('bot_reply_time') - F('created_at'),
                output_field=DurationField()
            )
        )

        avg_response_time = user_messages.aggregate(
            avg_time=Avg('response_time')
        )['avg_time'] or timedelta(0)

        # Calculate satisfaction rate
        feedback_count = Feedback.objects.count()
        useful_feedback_count = Feedback.objects.exclude(rating='other').count()
        satisfaction_rate = (useful_feedback_count / feedback_count * 100) if feedback_count else 0

        return Response({
            'total_users': total_users,
            'total_queries': total_queries,
            'avg_response_time_seconds': round(avg_response_time.total_seconds(), 2),
            'satisfaction_rate': round(satisfaction_rate, 2),
        })


class RecentQueriesAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        recent_user_msgs = Message.objects.filter(sender='user')\
            .select_related('conversation__user')\
            .order_by('-created_at')[:20]
        data = []
        for msg in recent_user_msgs:
            user = msg.conversation.user
            bot_replied = Message.objects.filter(
                conversation=msg.conversation,
                sender='bot',
                created_at__gt=msg.created_at
            ).exists()

            data.append({
                'user': user.get_full_name() or user.username,
                'query': msg.content,
                'status': 'Resolved' if bot_replied else 'In Progress',
                'timestamp': msg.created_at,
            })

        return Response(data)


class UserManagementAPIView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = UserManagementSerializer

    def get_queryset(self):
        return CustomUser.objects.annotate(
            queries=Count('conversations__messages', filter=models.Q(conversations__messages__sender='user')),
            last_active=Max('conversations__messages__created_at')
        )
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    # def list(self, request, *args, **kwargs):
    #     response = super().list(request, *args, **kwargs)
    #     # Add training status logic here
    #     for item in response.data:
    #         item['training_status'] = (
    #             'Required' if item['queries'] and item['queries'] > int(request.query_params.get('training_threshold', 30))
    #             else 'Up to date'
    #         )
    #     return response

class ExportUsersCSVAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        import csv
        from django.http import HttpResponse

        threshold = int(request.query_params.get('training_threshold', 30))
        users = CustomUser.objects.annotate(
            queries=Count('conversations__messages', filter=models.Q(conversations__messages__sender='user')),
            last_active=Max('conversations__messages__created_at')
        )

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="user_management.csv"'
        writer = csv.writer(response)
        writer.writerow(['ID', 'Username', 'Email', 'Full Name', 'Role', 'Active', 'Date Joined', 'Queries', 'Last Active', 'Training Status'])

        for u in users:
            status = 'Required' if u.queries > threshold else 'Up to date'
            writer.writerow([
                u.id, u.username, u.email,
                u.get_full_name() or u.username, u.role,
                u.is_active, u.date_joined, u.queries, u.last_active, status
            ])
        return response

from django.db.models.functions import TruncDate

class DailyActivityAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        data = (
            Message.objects
            .filter(sender='user')
            .annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(query_count=Count('id'))
            .order_by('date')
        )
        return Response(data)