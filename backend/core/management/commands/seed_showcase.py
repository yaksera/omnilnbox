"""Create a realistic demo shop ("Sita Kurta House") for sales demos, screenshots and training.

    python manage.py seed_showcase                       # demo@sitakurta.com / Kathmandu-Blue-42
    python manage.py seed_showcase --email you@x.com --password '...' --reset

Everything uses demo channels (no real messages are sent).
"""
import io
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

PRODUCTS = [
    ("Cotton kurta", "1800", 24, ["S", "M", "L", "XL"], (128, 30, 60), "Handmade cotton kurta with block print. Breathable, machine washable."),
    ("Silk saree", "6500", 7, ["Maroon", "Teal", "Gold"], (20, 110, 140), "Pure silk saree with zari border, blouse piece included."),
    ("Pashmina shawl", "3200", 3, [], (190, 140, 40), "Soft Nepali pashmina, 70x200 cm."),
    ("Dhaka topi", "650", 40, ["Small", "Medium", "Large"], (60, 60, 120), "Traditional Palpali Dhaka topi."),
    ("Kids kurta set", "1450", 0, ["2-3y", "4-5y", "6-7y"], (220, 120, 60), "Cotton kurta + pyjama set for kids."),
    ("Embroidered kurti", "2400", 12, ["S", "M", "L"], (100, 30, 110), "Hand-embroidered neckline, rayon fabric."),
]

THREADS = [
    ("whatsapp", "Anita Gurung", "+977 9812345678", [
        ("in", "Namaste! Is the maroon cotton kurta available in M size?", 180),
        ("out", "Namaste Anita ji! 🙏 Yes, M is available. It's Rs 1,800 + delivery.", 176),
        ("in", "Pokhara ma delivery huncha? Kati din lagcha?", 170),
    ]),
    ("instagram", "Priya Karki", "@priya.karki", [
        ("in", "Loved your latest reel 😍 is the teal saree still available?", 95),
    ]),
    ("messenger", "Bikash Rai", "", [
        ("in", "Mero order #1003 kaha pugyo? 3 din bhayo", 70),
        ("out", "Namaste Bikash ji, your parcel is with Nepal Can Move, reaching Dharan tomorrow. 🚚", 66),
        ("in", "Okay dhanyabad!", 64),
    ]),
    ("viber", "Sunita Shrestha", "+977 9841112233", [
        ("in", "Wholesale rate for 20 pcs Dhaka topi?", 40),
    ]),
    ("tiktok", "dancewithkiran", "@dancewithkiran", [
        ("in", "Saw your video! Where can I buy the kids kurta set?", 30),
    ]),
    ("telegram", "Rohan Joshi", "@rohanj", [
        ("in", "Do you accept eSewa?", 22),
        ("out", "Yes! Khalti, eSewa, bank transfer or cash on delivery. 😊", 20),
    ]),
    ("website", "Hari Bhandari", "9812300000", [
        ("in", "Do you deliver to Butwal? How many days?", 12),
    ]),
    ("gmail", "Emily Carter", "emily@boutique.co.uk", [
        ("in", "Hello! We're a boutique in London interested in stocking your pashmina shawls. Do you ship internationally?", 300),
    ]),
    ("whatsapp", "Maya Thapa", "+977 9801234567", [
        ("in", "Mero parcel ma size milena, exchange garna milcha?", 8),
    ]),
]

KNOWLEDGE = [
    ("Delivery charges and time", "Inside Kathmandu Valley: Rs 100, 1-2 days. Outside the Valley: Rs 150, 3-5 days (Pokhara, Butwal, Dharan 2-3 days). Free delivery on orders over Rs 5,000. International shipping on request."),
    ("Payment options", "Cash on delivery all over Nepal, Khalti, eSewa, or bank transfer (Nabil Bank). We send a secure payment link after confirming the order."),
    ("Exchange and return policy", "Exchange within 7 days if unused with tags. Size exchange is free inside the Valley. No refunds on sale items."),
    ("Size guide", "Kurta sizes: S (chest 36\"), M (38\"), L (40\"), XL (42\"). Kids sets by age. Ask us for exact measurements."),
    ("Shop location and hours", "Shop in New Road, Kathmandu (near Bishal Bazar). Open Sunday to Friday, 10am to 6pm. Closed on Saturdays."),
    ("Wholesale", "Wholesale price from 20 pieces: 15% off. Contact the owner for 100+ pieces."),
]


def _image(color):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    im = Image.new("RGB", (600, 600), (245, 240, 235))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([150, 90, 450, 540], radius=40, fill=color)
    d.polygon([(150, 160), (60, 300), (120, 330), (150, 260)], fill=color)
    d.polygon([(450, 160), (540, 300), (480, 330), (450, 260)], fill=color)
    d.ellipse([255, 80, 345, 150], fill=(245, 240, 235))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


class Command(BaseCommand):
    help = "Create the 'Sita Kurta House' demo workspace (demo channels, orders, AI, broadcasts, analytics)."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="demo@sitakurta.com")
        parser.add_argument("--password", default="Kathmandu-Blue-42")
        parser.add_argument("--reset", action="store_true", help="Delete the existing demo workspace first")

    @transaction.atomic
    def handle(self, *args, **o):
        from accounts.models import AuditLog, Profile
        from automations.models import AssistantSettings, KnowledgeItem, Rule
        from broadcasts.models import Broadcast
        from commerce.models import Customer, Order, OrderItem, PaymentLink, Product, ShopSettings
        from core.models import Membership, Workspace
        from inbox.models import CannedReply, Contact, Conversation, CsatResponse, Message, Tag
        from integrations.models import ChannelAccount
        from publishing.models import MediaAsset, Post, PostTarget, SocialAccount

        random.seed(7)
        User = get_user_model()
        now = timezone.now()
        user = User.objects.filter(username=o["email"]).first()
        if user and o["reset"]:
            Workspace.objects.filter(memberships__user=user, memberships__role="owner").delete()
        if user is None:
            user = User.objects.create_user(username=o["email"], email=o["email"], password=o["password"], first_name="Sita", last_name="Sharma")
        Profile.objects.update_or_create(user=user, defaults={"email_verified": True})
        if Workspace.objects.filter(memberships__user=user, name="Sita Kurta House").exists():
            self.stdout.write("Demo workspace already exists (use --reset to recreate).")
            return
        ws = Workspace.objects.create(name="Sita Kurta House", slug=f"sita-kurta-{random.randint(1000, 9999)}", plan="business",
                                      plan_expires_at=now + timedelta(days=365), csat_enabled=True)
        Membership.objects.create(user=user, workspace=ws, role="owner")
        team = []
        for first, last, role in [("Ram", "Thapa", "agent"), ("Maya", "Gurung", "supervisor")]:
            email = f"{first.lower()}.{o['email']}"
            u = User.objects.filter(username=email).first() or User.objects.create_user(username=email, email=email, password=o["password"], first_name=first, last_name=last)
            Membership.objects.get_or_create(user=u, workspace=ws, defaults={"role": role})
            team.append(u)
        ram, maya = team

        tags = {n: Tag.objects.create(workspace=ws, name=n, color=c) for n, c in
                [("VIP", "#ca8a04"), ("Pokhara", "#0891b2"), ("Wholesale", "#7c3aed"), ("Order", "#16a34a"), ("Complaint", "#dc2626")]}
        for sc, title, body in [("delivery", "Delivery info", "Inside the Valley Rs 100 (1-2 days), outside Rs 150 (3-5 days). 🚚"),
                                ("pay", "Payment options", "Khalti, eSewa, bank transfer or cash on delivery. 😊"),
                                ("thanks", "Thank you", "Dhanyabad! 🙏 Let us know if you need anything else.")]:
            CannedReply.objects.create(workspace=ws, shortcut=sc, title=title, body=body, created_by=user)

        # Channels (demo = nothing is sent anywhere)
        channels = {}
        for prov, name in [("whatsapp", "Shop WhatsApp"), ("instagram", "@sitakurtahouse"), ("messenger", "Sita Kurta House Page"),
                           ("tiktok", "@sitakurta"), ("viber", "Sita Kurta Viber"), ("telegram", "@SitaKurtaBot"), ("gmail", "orders@sitakurta.com")]:
            channels[prov] = ChannelAccount.objects.create(workspace=ws, provider=prov, name=name, is_demo=True, status="active", created_by=user)
        channels["website"] = ChannelAccount.objects.create(workspace=ws, provider="website", name="sitakurta.com", status="active", created_by=user,
                                                            credentials={"title": "Chat with Sita Kurta House", "color": "#0f766e",
                                                                         "greeting": "Namaste! 👋 Ask us about sizes, prices or delivery.", "ask_contact": "optional"})

        convs = {}
        for prov, name, handle, msgs in THREADS:
            ch = channels[prov]
            contact = Contact.objects.create(workspace=ws, channel=ch, external_id=f"{prov}-{name}", name=name, handle=handle)
            conv = Conversation.objects.create(workspace=ws, channel=ch, contact=contact, external_thread_id=f"{prov}-{name}",
                                               subject="Wholesale enquiry: pashmina shawls" if prov == "gmail" else "")
            for direction, text, mins in msgs:
                at = now - timedelta(minutes=mins)
                Message.objects.create(conversation=conv, direction=direction, text=text, sent_at=at, sender_name="" if direction == "in" else "Sita Sharma",
                                       sent_by=user if direction == "out" else None, status="received" if direction == "in" else "sent")
            last = msgs[-1]
            conv.last_message_at = now - timedelta(minutes=last[2])
            conv.last_message_preview = last[1][:300]
            conv.unread_count = sum(1 for m in msgs if m[0] == "in") if last[0] == "in" else 0
            if any(m[0] == "out" for m in msgs):
                conv.first_response_at = now - timedelta(minutes=[m[2] for m in msgs if m[0] == "out"][0])
            conv.save()
            convs[name] = conv
        convs["Anita Gurung"].tags.add(tags["Pokhara"], tags["Order"])
        convs["Sunita Shrestha"].tags.add(tags["Wholesale"])
        convs["Maya Thapa"].tags.add(tags["Complaint"])
        convs["Bikash Rai"].assigned_to = ram
        convs["Bikash Rai"].save(update_fields=["assigned_to"])
        convs["Anita Gurung"].meta = {"ai_category": "order", "ai_sentiment": "positive", "ai_summary": {
            "summary": "Anita wants the maroon cotton kurta in M and asks about delivery to Pokhara.", "category": "order",
            "sentiment": "positive", "next_step": "Confirm Rs 150 delivery (3 days) and create the order.", "at": now.isoformat()}}
        convs["Anita Gurung"].save(update_fields=["meta"])
        # an AI bot conversation + handoff note
        ai_conv = convs["Rohan Joshi"]
        Message.objects.filter(conversation=ai_conv, direction="out").update(bot="ai", sender_name="Assistant", sent_by=None)
        # a public comment thread
        page = channels["messenger"]
        gc = Contact.objects.create(workspace=ws, channel=page, external_id="commenter:U9", name="Gita Rai")
        cc = Conversation.objects.create(workspace=ws, channel=page, contact=gc, external_thread_id="comment:P_1:U9", subject="Comment on your post",
                                         meta={"kind": "comment", "post_id": "P_1", "last_comment_id": "C1"},
                                         last_message_at=now - timedelta(minutes=15), last_message_preview="Price kati ho yo kurta ko? 😍", unread_count=1)
        Message.objects.create(conversation=cc, direction="in", text="Price kati ho yo kurta ko? 😍", sent_at=now - timedelta(minutes=15))

        # AI + automations
        AssistantSettings.objects.update_or_create(workspace=ws, defaults={
            "business_name": "Sita Kurta House", "tone": "friendly", "bot_mode": "after_hours", "auto_tag": True,
            "about": "We sell handmade cotton kurtas, silk sarees, pashmina shawls and Dhaka topi from our shop in New Road, Kathmandu. "
                     "Delivery all over Nepal. Payment: cash on delivery, Khalti, eSewa or bank transfer."})
        for t, c in KNOWLEDGE:
            KnowledgeItem.objects.create(workspace=ws, title=t, content=c)
        for name, trig, kw, text, ai, runs, ch in [
            ("Price comments → DM", "comment", ["price", "kati", "rate", "details"], "Namaste {name}! 🙏 Here are the details and prices. Reply here to order!", True, 146, page),
            ("Welcome message", "welcome", [], "Namaste {name}! 🙏 Thanks for messaging Sita Kurta House. How can we help you today?", False, 312, None),
            ("Away message", "away", [], "Thanks for your message! We're closed now and will reply from 10am (Sun-Fri).", False, 58, None),
            ("Price question", "keyword", ["price", "kati", "rate", "cost"], "Hi {name}! Our latest prices: kurtas from Rs 1,800, sarees from Rs 6,500.", True, 89, None)]:
            Rule.objects.create(workspace=ws, name=name, trigger=trig, keywords=kw, reply_text=text, use_ai=ai, run_count=runs,
                                last_run_at=now - timedelta(minutes=random.randint(5, 400)), channel=ch,
                                public_reply_text="Hi {name}, we've sent you the details in your inbox 📩" if trig == "comment" else "")

        # Shop
        ShopSettings.objects.update_or_create(workspace=ws, defaults={
            "bank_details": "Nabil Bank · Sita Kurta House\nAccount: 01234567890123\nBranch: New Road", "esewa_merchant_code": "EPAYTEST",
            "secrets": {"khalti_secret_key": "test_secret_key_demo", "esewa_secret_key": "8gBm/:&EnhH.1/q", "ncm_token": "demo-token"},
            "next_order_number": 1001})
        products = []
        for name, price, stock, variants, color, desc in PRODUCTS:
            img = None
            data = _image(color)
            if data:
                img = MediaAsset(workspace=ws, kind="image", mime="image/jpeg", size=len(data), original_name=f"{name}.jpg", uploaded_by=user)
                img.file.save("product.jpg", ContentFile(data), save=False)
                img.save()
            products.append(Product.objects.create(workspace=ws, name=name, price=Decimal(price), stock=stock, variants=variants,
                                                   description=desc, image=img))
        customers = {}
        for name, phone, city, district in [("Anita Gurung", "9812345678", "Lakeside, Pokhara", "Kaski"), ("Bikash Rai", "9842233445", "Dharan", "Sunsari"),
                                            ("Priya Karki", "9803344556", "Baneshwor", "Kathmandu"), ("Rohan Joshi", "9851122334", "Jhamsikhel", "Lalitpur"),
                                            ("Sunita Shrestha", "9841112233", "Butwal", "Rupandehi"), ("Maya Thapa", "9801234567", "Bhaktapur", "Bhaktapur")]:
            customers[name] = Customer.objects.create(workspace=ws, name=name, phone=phone, city=city, district=district, address="Ward 6, near the temple")
            if name in convs:
                Contact.objects.filter(pk=convs[name].contact_id).update(customer=customers[name])
        orders_spec = [
            ("Anita Gurung", [(0, "M", 1), (2, "", 1)], "esewa", "pending", "new", 0.1),
            ("Bikash Rai", [(1, "Teal", 1)], "cod", "unpaid", "shipped", 3),
            ("Priya Karki", [(5, "M", 2)], "khalti", "paid", "packed", 1),
            ("Rohan Joshi", [(3, "Medium", 3)], "khalti", "paid", "delivered", 6),
            ("Sunita Shrestha", [(3, "Large", 20)], "bank", "paid", "confirmed", 2),
            ("Maya Thapa", [(0, "L", 1)], "cod", "paid", "delivered", 9),
            ("Priya Karki", [(1, "Maroon", 1)], "cod", "unpaid", "cancelled", 12),
            ("Anita Gurung", [(2, "", 2)], "khalti", "paid", "delivered", 20),
        ]
        for i, (cname, items, method, pay, status, days) in enumerate(orders_spec):
            c = customers[cname]
            at = now - timedelta(days=days)
            conv = convs.get(cname)
            o_ = Order.objects.create(workspace=ws, number=f"#{1001 + i}", customer=c, conversation=conv, status=status, payment_method=method,
                                      payment_status=pay, recipient_name=c.name, recipient_phone=c.phone, address=c.address, city=c.city,
                                      district=c.district, delivery_charge=Decimal("100" if c.district in ("Kathmandu", "Lalitpur", "Bhaktapur") else "150"),
                                      created_by=user, paid_at=at + timedelta(hours=2) if pay == "paid" else None)
            for pi, variant, qty in items:
                OrderItem.objects.create(order=o_, product=products[pi], name=products[pi].name, variant=variant, quantity=qty, unit_price=products[pi].price)
            if cname == "Sunita Shrestha":
                o_.discount = Decimal("1950")
            o_.subtotal = sum((it.unit_price * it.quantity for it in o_.items.all()), Decimal("0"))
            o_.total = o_.subtotal + o_.delivery_charge - o_.discount
            o_.history = [{"at": at.isoformat(), "text": f"Order created ({o_.get_payment_method_display()})", "by": "Sita Sharma"}]
            if status in ("shipped", "delivered"):
                o_.courier, o_.courier_name, o_.courier_ref, o_.tracking_id = "ncm", "Nepal Can Move", f"55{i}1", f"NCM55{i}1"
                o_.tracking_url = f"https://nepalcanmove.com/track/NCM55{i}1"
                o_.delivery_status = "Delivered" if status == "delivered" else "Arrived at branch"
                o_.shipped_at = at + timedelta(days=1)
                o_.history.append({"at": (at + timedelta(days=1)).isoformat(), "text": "Shipped with Nepal Can Move (tracking NCM55%d1)" % i, "by": "Sita Sharma"})
            o_.save()
            Order.objects.filter(pk=o_.pk).update(created_at=at)
            if pay == "pending":
                PaymentLink.objects.create(order=o_, amount=o_.total, gateway="")
        ShopSettings.objects.filter(workspace=ws).update(next_order_number=1001 + len(orders_spec))

        # Publishing
        acc = [SocialAccount.objects.create(workspace=ws, platform=p, external_id=f"demo-{p}", name=n, credentials={"demo": True}, created_by=user)
               for p, n in [("facebook", "Sita Kurta House"), ("instagram", "sitakurtahouse"), ("youtube", "Sita Kurta House"), ("tiktok", "sitakurta")]]
        for cap, days, status in [("Dashain collection is here! 🎉 20% off all kurtas until Oct 15. #Dashain #Kurta", -1, "published"),
                                  ("New silk sarees in teal and gold ✨ Limited stock.", 2, "scheduled"),
                                  ("Tihar gift ideas: pashmina shawls from Rs 3,200 🪔", 9, "scheduled"),
                                  ("Behind the scenes: block printing our kurtas 🎨", 15, "draft")]:
            when = now + timedelta(days=days)
            post = Post.objects.create(workspace=ws, created_by=user, caption=cap, status=status, media=products[0].image,
                                       scheduled_at=when if status != "draft" else None, published_at=when if status == "published" else None)
            for a in acc[:2]:
                PostTarget.objects.create(post=post, account=a, status="published" if status == "published" else "pending",
                                          url="https://facebook.com/" if status == "published" else "")

        # Broadcasts (history)
        for name, ch, text, total, days in [("Dashain sale 2026", channels["whatsapp"], "Hi {{1}}! 🎉 Dashain sale: 20% off all kurtas until Oct 15.", 412, 3),
                                            ("New arrivals", channels["viber"], "Namaste {name}! New silk sarees just arrived ✨", 128, 10)]:
            Broadcast.objects.create(workspace=ws, name=name, channel=ch, kind="template" if ch.provider == "whatsapp" else "text",
                                     template_name="dashain_offer" if ch.provider == "whatsapp" else "", template_language="en",
                                     template_body=text, text=text, variables=["{name}"], status="done", total=total, sent=total - 3,
                                     failed=3, created_by=user, started_at=now - timedelta(days=days), finished_at=now - timedelta(days=days))

        # Analytics history: 14 days of messages, first responses and ratings
        hist_ch = channels["whatsapp"]
        for d in range(14):
            for k in range(random.randint(4, 11)):
                ct = Contact.objects.create(workspace=ws, channel=hist_ch, external_id=f"hist-{d}-{k}", name=random.choice(
                    ["Sagar", "Pooja", "Nabin", "Asha", "Kiran", "Dipesh", "Sarita", "Bishal"]) + " " + random.choice(["KC", "Adhikari", "Tamang", "Magar", "Poudel"]))
                t0 = now - timedelta(days=d, hours=random.randint(1, 9))
                cv = Conversation.objects.create(workspace=ws, channel=hist_ch, contact=ct, external_thread_id=f"hist-{d}-{k}", status="closed",
                                                 last_message_at=t0 + timedelta(minutes=30), last_message_preview="Dhanyabad!")
                Conversation.objects.filter(pk=cv.pk).update(created_at=t0)
                reply_after = random.choice([3, 5, 8, 12, 20, 35, 50, 75, 130])
                agent = random.choice([user, ram, maya])
                Message.objects.create(conversation=cv, direction="in", text="Size available cha?", sent_at=t0)
                Message.objects.create(conversation=cv, direction="out", text="Cha! 😊", sent_at=t0 + timedelta(minutes=reply_after), sent_by=agent,
                                       sender_name=agent.get_full_name(), status="sent")
                Message.objects.create(conversation=cv, direction="in", text="Dhanyabad!", sent_at=t0 + timedelta(minutes=reply_after + 3))
                cv.first_response_at = t0 + timedelta(minutes=reply_after)
                cv.save(update_fields=["first_response_at"])
                if random.random() < 0.45:
                    r = CsatResponse.objects.create(workspace=ws, conversation=cv, agent=agent, score=random.choice([5, 5, 5, 4, 4, 3, 5, 2]),
                                                    comment=random.choice(["", "", "Fast reply, thank you!", "Very helpful 🙏", "Delivery was late"]))
                    CsatResponse.objects.filter(pk=r.pk).update(created_at=t0 + timedelta(hours=2))

        for action, target, mins in [("auth.login", o["email"], 5), ("team.invited", ram.email, 3000), ("channel.connected", "WhatsApp: Shop WhatsApp", 2900),
                                     ("automation.created", "Price comments → DM", 2000), ("payments.settings_changed", "Khalti", 1500),
                                     ("broadcast.sent", "Dashain sale 2026", 4320), ("order.status", "#1004", 300)]:
            e = AuditLog.objects.create(workspace=ws, actor=user, actor_label="Sita Sharma", action=action, target=target, ip="103.10.28.14")
            AuditLog.objects.filter(pk=e.pk).update(created_at=now - timedelta(minutes=mins))
        self.stdout.write(self.style.SUCCESS(f"Demo workspace ready. Log in as {o['email']} / {o['password']}"))
