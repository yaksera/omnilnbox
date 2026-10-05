"""Website chat widget: a chat bubble on the shop's own website.

Visitors chat through /widget/<channel_id> (loaded in an iframe by widget.js); messages are stored
like any other channel, and agent replies are picked up by the widget's polling. Nothing to call.
"""
import uuid

from .base import BaseProvider, Field


class WebsiteProvider(BaseProvider):
    key = "website"
    label = "Website chat"
    category = "chat"
    color = "#0F766E"
    receive_mode = "widget"
    fields = [
        Field("title", "Widget title", required=False, default="Chat with us", help="Shown at the top of the chat window."),
        Field("greeting", "Greeting", required=False, default="Hi! 👋 How can we help you today?",
              help="First message visitors see."),
        Field("color", "Colour", required=False, default="#4f46e5", help="Hex colour of the chat button, e.g. #4f46e5."),
        Field("ask_contact", "Ask for name & phone first", type="select", required=False, default="optional",
              options=["optional", "required", "no"]),
        # Abuse / AI-cost protection (the widget is public: anyone can type into it)
        Field("max_chars", "Longest message a visitor can send (characters)", type="select", required=False,
              default="1000", options=["300", "500", "1000", "2000"],
              help="Stops people pasting huge texts. Longer messages are refused with a friendly note."),
        Field("ai_per_visitor", "AI replies per visitor per day", type="select", required=False, default="20",
              options=["5", "10", "20", "50", "100"],
              help="After this, the AI stops in that chat and your team takes over (the visitor is told)."),
        Field("ai_per_day", "AI replies per day on this widget (all visitors)", type="select", required=False,
              default="300", options=["50", "100", "300", "1000", "3000"],
              help="A hard daily budget for AI on this website. Messages still reach your inbox after it."),
    ]
    setup_steps = [
        "Save this channel.",
        "Copy the embed code shown on the channel card.",
        "Paste it before </body> on every page of your website (or in your site builder's 'custom code' box).",
        "Visitors click the chat bubble; their messages appear here and your replies appear on the website.",
    ]

    @staticmethod
    def limits(creds):
        """Protection limits for a website widget, with safe defaults for channels created before they existed."""
        def num(key, default):
            try:
                return max(1, int(str((creds or {}).get(key) or default)))
            except ValueError:
                return default
        return {"max_chars": num("max_chars", 1000), "ai_per_visitor": num("ai_per_visitor", 20),
                "ai_per_day": num("ai_per_day", 300)}

    def verify(self):
        color = str(self.creds.get("color") or "#4f46e5")
        if not (len(color) == 7 and color.startswith("#")):
            self.creds["color"] = "#4f46e5"
            self.channel.credentials = self.creds
        return {}

    can_send_media = True

    def send_media(self, conversation, files, text=""):
        return f"web-{uuid.uuid4().hex[:16]}"  # the widget shows the files itself

    def send(self, conversation, text):
        return f"web-{uuid.uuid4().hex[:16]}"  # the widget fetches new messages itself
