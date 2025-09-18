from rest_framework import serializers
from accounts.models import CustomUser

class UserManagementSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    queries = serializers.IntegerField(read_only=True)
    last_active = serializers.DateTimeField(read_only=True)
    training_status = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'full_name',
            'role', 'is_active', 'date_joined',
            'queries', 'last_active', 'training_status',
        ]

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_training_status(self, obj):
        threshold = int(self.context['request'].query_params.get('training_threshold', 30))
        return 'Required' if obj.queries > threshold else 'Up to date'
