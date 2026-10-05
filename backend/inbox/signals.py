"""Tell open browsers (core.realtime) whenever inbox data changes."""
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from core.realtime import bump

from .models import Attachment, Conversation, Message


def _workspace_of_message(msg):
    conv = msg._state.fields_cache.get("conversation")
    if conv is not None:
        return conv.workspace_id
    return Conversation.objects.filter(id=msg.conversation_id).values_list("workspace_id", flat=True).first()


@receiver(post_save, sender=Message)
def _message_saved(sender, instance, **kwargs):
    bump(_workspace_of_message(instance))


@receiver(post_save, sender=Conversation)
def _conversation_saved(sender, instance, **kwargs):
    bump(instance.workspace_id)


@receiver(post_save, sender=Attachment)
def _attachment_saved(sender, instance, **kwargs):
    if instance.message_id:
        bump(instance.workspace_id)


@receiver(m2m_changed, sender=Conversation.tags.through)
def _tags_changed(sender, instance, action, **kwargs):
    if action.startswith("post_") and isinstance(instance, Conversation):
        bump(instance.workspace_id)
