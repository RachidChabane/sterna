from rest_framework import serializers
from .models import SupportRequest


class SupportRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportRequest
        fields = ["email", "subject", "message", "context"]

    def validate_message(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Message must be at least 10 characters.")
        return value
