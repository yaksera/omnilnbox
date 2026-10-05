"""Keep a Discord Gateway connection open for every connected Discord channel.

    pip install discord.py
    python manage.py run_discord

New Discord channels are picked up every 60 seconds.
"""
import asyncio

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Listen for Discord messages over the Gateway."

    def handle(self, *args, **opts):
        try:
            import discord  # noqa: F401
        except ImportError as exc:
            raise CommandError("Install discord.py first: pip install discord.py") from exc
        asyncio.run(self.main())

    async def main(self):
        import discord

        from inbox.services import ingest_message
        from integrations.models import ChannelAccount
        from integrations.providers import get_provider

        running = {}

        def make_client(channel_id):
            intents = discord.Intents.default()
            intents.message_content = True
            intents.dm_messages = True
            client = discord.Client(intents=intents)

            @client.event
            async def on_ready():
                self.stdout.write(self.style.SUCCESS(f"Discord bot {client.user} online for channel {channel_id}"))

            @client.event
            async def on_message(message):
                channel = await sync_to_async(ChannelAccount.objects.get)(id=channel_id)
                provider = get_provider(channel)
                raw = {
                    "id": str(message.id),
                    "channel_id": str(message.channel.id),
                    "guild_id": str(message.guild.id) if message.guild else None,
                    "content": message.content,
                    "timestamp": message.created_at.isoformat(),
                    "attachments": [{"url": a.url, "filename": a.filename, "content_type": a.content_type or ""}
                                    for a in message.attachments],
                    "author": {
                        "id": str(message.author.id), "username": message.author.name,
                        "global_name": getattr(message.author, "global_name", None), "bot": message.author.bot,
                    },
                }
                # In servers only react when the bot is mentioned
                if message.guild and client.user not in message.mentions and message.author != client.user:
                    return
                item = provider.to_incoming(raw)
                if item:
                    await sync_to_async(ingest_message)(channel, item)

            return client

        while True:
            channels = await sync_to_async(list)(
                ChannelAccount.objects.filter(provider="discord", is_demo=False).exclude(status="disabled")
            )
            for ch in channels:
                if str(ch.id) in running:
                    continue
                token = ch.credentials.get("bot_token")
                if not token:
                    continue
                client = make_client(str(ch.id))
                running[str(ch.id)] = asyncio.create_task(client.start(token))
            await asyncio.sleep(60)
