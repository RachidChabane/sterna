import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from .models import SupportRequest
from .serializers import SupportRequestCreateSerializer
from .throttles import SupportAnonThrottle, SupportUserThrottle
from . import notifications as support_notifications

logger = logging.getLogger(__name__)


class SupportRequestCreateView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [SupportAnonThrottle, SupportUserThrottle]

    def post(self, request):
        serializer = SupportRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user if request.user.is_authenticated else None

        email = serializer.validated_data.get("email") or (user.email if user else "")

        instance = SupportRequest.objects.create(
            user=user,
            email=email,
            subject=serializer.validated_data["subject"],
            message=serializer.validated_data["message"],
            context=serializer.validated_data.get("context", {}),
        )

        try:
            support_notifications.send_support_request_received_email(instance)
        except Exception:
            logger.exception("Failed to send support ack email for %s", instance.id)

        try:
            support_notifications.post_to_slack(instance)
        except Exception:
            logger.exception("Failed to post support request to Slack for %s", instance.id)

        return Response(
            {"id": str(instance.id), "message": "Your request has been received."},
            status=status.HTTP_201_CREATED,
        )
