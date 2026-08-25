"""Regression coverage for the conversations<->sparks registration point.

conversations/serializers.py renders a message's or chat's nested
"sparks" field through a serializer registered by the sparks app (see
register_spark_serializer), rather than importing sparks.serializers
directly — that indirection is what keeps the dependency edge pointing
one way (sparks -> conversations only).

That indirection has a failure mode ordinary "the suite is green" runs
would miss: if the sparks app fails to register itself, get_sparks()
falls back to returning an empty list, and nothing else in the test
suite creates a Spark and reads it back through these serializers.
These tests lock both halves: that the registration actually happened
during app startup, and that a real Spark round-trips through it.
"""

import pytest

from authentication.models import User
from conversations.models import Chat, Conversation, Message
from conversations.serializers import (
    ChatSerializer,
    MessageSerializer,
    _spark_serializer_class,
)
from sparks.models import Spark
from sparks.serializers import MessageSparkSerializer


def test_sparks_app_registered_its_serializer():
    """AppConfig.ready() must have wired sparks into conversations by now."""
    assert _spark_serializer_class is MessageSparkSerializer


def test_get_sparks_schema_annotation_present():
    """The OpenAPI hint for the method field must carry the real item type,
    not an unannotated (and therefore mistyped) SerializerMethodField.
    """
    for serializer_class in (MessageSerializer, ChatSerializer):
        annotation = getattr(
            serializer_class.get_sparks, '_spectacular_annotation', None
        )
        assert annotation is not None
        # many=True wraps the child serializer in a ListSerializer.
        assert isinstance(annotation['field'].child, MessageSparkSerializer)


@pytest.mark.django_db
def test_message_serializer_nests_real_spark_data():
    """A Spark attached to a message must round-trip through MessageSerializer."""
    user = User.objects.create_user(email='sparks-regress@example.com', password='x')
    conversation = Conversation.objects.create(user=user)
    chat = Chat.objects.create(conversation=conversation)
    message = Message.objects.create(chat=chat, role=Message.ROLE_ASSISTANT)
    spark = Spark.objects.create(
        user=user,
        chat=chat,
        message=message,
        title='Regression Spark',
        framework=Spark.Framework.REACT,
    )
    spark.save_code('export default function App() { return null; }')
    spark.save()

    data = MessageSerializer(message).data

    assert len(data['sparks']) == 1
    nested = data['sparks'][0]
    assert nested['id'] == str(spark.id)
    assert set(nested.keys()) == set(MessageSparkSerializer.Meta.fields)


@pytest.mark.django_db
def test_chat_serializer_nests_real_spark_data():
    """A Spark attached to a chat (no message) must round-trip through ChatSerializer."""
    user = User.objects.create_user(email='sparks-regress-2@example.com', password='x')
    conversation = Conversation.objects.create(user=user)
    chat = Chat.objects.create(conversation=conversation)
    spark = Spark.objects.create(
        user=user,
        chat=chat,
        title='Regression Chat Spark',
        framework=Spark.Framework.HTML,
    )
    spark.save_code('<html></html>')
    spark.save()

    data = ChatSerializer(chat).data

    assert len(data['sparks']) == 1
    assert data['sparks'][0]['id'] == str(spark.id)
