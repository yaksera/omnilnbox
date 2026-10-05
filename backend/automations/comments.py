"""Comment-to-DM: answer Facebook Page / Instagram post comments with a private message.

Comments arrive by webhook (Page "feed" field / Instagram "comments" field) and, as a fallback that
also works while the Meta app is in Development mode, by polling the latest posts' comments.
Meta allows one private reply per comment, within 7 days of the comment.
"""
import json
import logging
from datetime import datetime, timedelta
from datetime import timezone as dt_tz

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from billing.plans import F_AI, F_AUTOMATIONS

from . import ai, llm
from .models import ProcessedComment, Rule

logger = logging.getLogger(__name__)
PROVIDERS = ("messenger", "instagram")


def _own_id(channel):
    c = channel.credentials or {}
    return str(c.get("page_id") or c.get("ig_account_id") or "")


def comment_rules(channel):
    from django.db.models import Q
    if channel.provider not in PROVIDERS or channel.is_demo or not channel.workspace.has_feature(F_AUTOMATIONS):
        return Rule.objects.none()
    return Rule.objects.filter(workspace=channel.workspace, enabled=True, trigger=Rule.COMMENT).filter(
        Q(channel=channel) | Q(channel__isnull=True))


# ------------------------------------------------------------------ reading comments
def from_webhook(channel, raw_body):
    """Extract new comments from a Meta webhook payload."""
    try:
        body = json.loads(raw_body or b"{}")
    except ValueError:
        return []
    out = []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            v = change.get("value") or {}
            if channel.provider == "messenger" and change.get("field") == "feed":
                if v.get("item") == "comment" and v.get("verb") == "add" and v.get("comment_id"):
                    created = v.get("created_time")
                    out.append({
                        "id": str(v["comment_id"]), "post_id": str(v.get("post_id", "")), "text": v.get("message", ""),
                        "from_id": str((v.get("from") or {}).get("id", "")), "from_name": (v.get("from") or {}).get("name", ""),
                        "created": datetime.fromtimestamp(int(created), tz=dt_tz.utc) if created else timezone.now(),
                    })
            elif channel.provider == "instagram" and change.get("field") == "comments" and v.get("id"):
                out.append({
                    "id": str(v["id"]), "post_id": str((v.get("media") or {}).get("id", "")), "text": v.get("text", ""),
                    "from_id": str((v.get("from") or {}).get("id", "")), "from_name": (v.get("from") or {}).get("username", ""),
                    "created": timezone.now(),
                })
    return out


def poll(channel):
    """Latest comments on the 10 most recent posts (fallback for missing webhooks)."""
    from integrations.providers import get_provider
    provider = get_provider(channel)
    token = channel.credentials.get("page_access_token", "")
    own = _own_id(channel)
    if channel.provider == "messenger":
        data = provider.graph("GET", f"{own}/feed", token, params={
            "fields": "id,comments.order(reverse_chronological).limit(25){id,message,from,created_time}", "limit": "10"})
        text_key, time_key = "message", "created_time"
    else:
        data = provider.graph("GET", f"{own}/media", token, params={
            "fields": "id,comments.limit(25){id,text,username,from,timestamp}", "limit": "10"})
        text_key, time_key = "text", "timestamp"
    out = []
    for post in data.get("data", []):
        for c in (post.get("comments") or {}).get("data", []):
            who = c.get("from") or {}
            out.append({
                "id": str(c.get("id")), "post_id": str(post.get("id", "")), "text": c.get(text_key, ""),
                "from_id": str(who.get("id", "")), "from_name": who.get("name") or who.get("username") or c.get("username", ""),
                "created": parse_datetime(c[time_key]) if c.get(time_key) else timezone.now(),
            })
    return out


# ------------------------------------------------------------------ answering
def _post_matches(rule, post_id):
    if not rule.post_id:
        return True
    want = rule.post_id.strip()
    # Facebook post ids look like "<pageid>_<postid>"; accept either form
    return post_id == want or post_id.split("_")[-1] == want.split("_")[-1]


def _ai_dm(channel, comment, rule):
    from types import SimpleNamespace
    ws = channel.workspace
    fake = SimpleNamespace(workspace=ws, contact=SimpleNamespace(name=comment["from_name"]),
                           channel=SimpleNamespace(get_provider_display=channel.get_provider_display))
    history = [{"role": "user", "content": f"(Comment on our post) {comment['text'][:1000]}"}]
    return ai.bot_answer(fake, history=history)["reply"]


def handle(channel, comment, rules=None):
    """Answer one comment with the first matching rule. Returns the rule used, or None."""
    rules = list(rules if rules is not None else comment_rules(channel))
    if not rules or not comment.get("id") or (comment.get("from_id") and comment["from_id"] == _own_id(channel)):
        return None
    created = comment.get("created") or timezone.now()
    if timezone.now() - created > timedelta(days=7):
        return None  # Meta's private-reply window has passed
    rule = next((r for r in rules if r.created_at <= created + timedelta(minutes=1)
                 and _post_matches(r, comment.get("post_id", "")) and r.matches(comment.get("text", ""))), None)
    try:
        with transaction.atomic():
            ProcessedComment.objects.create(channel=channel, comment_id=comment["id"], rule=rule)
    except IntegrityError:
        return None  # already handled (webhook + polling can both see it)
    if rule is None:
        return None

    from integrations.providers import get_provider
    provider = get_provider(channel)
    token = channel.credentials.get("page_access_token", "")
    first = (comment.get("from_name") or "").split(" ")[0] or "there"
    text = ""
    if rule.use_ai and channel.workspace.has_feature(F_AI) and llm.configured():
        try:
            text = _ai_dm(channel, comment, rule)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI comment reply failed: %s", exc)
    text = text or (rule.reply_text or "").replace("{name}", first).replace("{first_name}", first).strip()
    error = ""
    try:
        if text:
            provider.graph("POST", "me/messages", token, json={
                "recipient": {"comment_id": comment["id"]}, "message": {"text": text[:2000]}})
        if rule.public_reply_text:
            public = rule.public_reply_text.replace("{name}", first).replace("{first_name}", first)
            path = f"{comment['id']}/comments" if channel.provider == "messenger" else f"{comment['id']}/replies"
            provider.graph("POST", path, token, json={"message": public[:500]})
    except Exception as exc:  # noqa: BLE001
        error = str(exc)[:500]
        logger.warning("Comment reply failed for %s: %s", comment["id"], error)
    Rule.objects.filter(pk=rule.pk).update(run_count=rule.run_count + 1, last_run_at=timezone.now(), last_error=error)
    return rule


def ingest(channel, comment):
    """Put a comment in the inbox as its own conversation (one thread per person per post)."""
    from integrations.providers import IncomingMessage
    from inbox.services import ingest_message
    if not comment.get("id") or (comment.get("from_id") and comment["from_id"] == _own_id(channel)):
        return None
    who = comment.get("from_id") or comment["id"]
    return ingest_message(channel, IncomingMessage(
        external_thread_id=f"comment:{comment.get('post_id', '')}:{who}"[:500], contact_external_id=f"commenter:{who}",
        contact_name=comment.get("from_name", ""), contact_handle=f"@{comment['from_name']}" if channel.provider == "instagram" and comment.get("from_name") else "",
        text=comment.get("text") or "[comment]", external_message_id=f"cmt:{comment['id']}", sent_at=comment.get("created"),
        subject="Comment on your post",
        thread_meta={"kind": "comment", "post_id": comment.get("post_id", ""), "last_comment_id": comment["id"]},
    ))


def handle_webhook(channel, raw_body):
    comments = from_webhook(channel, raw_body)
    if channel.provider not in PROVIDERS or channel.is_demo:
        return 0
    for c in comments:
        ingest(channel, c)
    rules = list(comment_rules(channel))
    return sum(1 for c in comments if handle(channel, c, rules)) if rules else 0


def poll_channel(channel):
    comments = poll(channel)
    baseline = channel.state.get("comments_baseline")
    if not baseline:
        # First look at this Page: remember what's already there; only newer comments reach the inbox/automations.
        for c in comments:
            ProcessedComment.objects.get_or_create(channel=channel, comment_id=c["id"])
        channel.state["comments_baseline"] = timezone.now().isoformat()
        channel.save(update_fields=["state"])
        return 0
    since = datetime.fromisoformat(baseline)
    fresh = [c for c in comments if (c.get("created") or timezone.now()) >= since]
    for c in fresh:
        ingest(channel, c)
    rules = list(comment_rules(channel))
    return sum(1 for c in fresh if handle(channel, c, rules)) if rules else 0


def poll_all():
    """Every Facebook Page / Instagram channel: comments into the inbox + comment-to-DM rules."""
    from integrations.models import ChannelAccount
    total = 0
    for ch in ChannelAccount.objects.filter(provider__in=PROVIDERS, is_demo=False) \
            .exclude(status=ChannelAccount.STATUS_DISABLED).select_related("workspace"):
        if ch.state.get("comments_inbox") is False and not comment_rules(ch).exists():
            continue
        try:
            total += poll_channel(ch)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Comment polling failed for %s: %s", ch, exc)
    return total
