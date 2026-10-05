import logging
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.audit import audit
from billing.plans import F_COURIERS, F_ORDERS
from core.permissions import require, require_feature
from core.tenancy import get_membership
from inbox.models import Conversation
from inbox.views import visible_conversations
from publishing import media as media_utils
from publishing.models import MediaAsset

from . import delivery, payment_check, payments, services
from .models import Booking, Customer, Order, PaymentCheck, PaymentLink, Product, ShopSettings

logger = logging.getLogger(__name__)
SECRET_FIELDS = ("khalti_secret_key", "esewa_secret_key", "ncm_token")


def _ws(request, feature=F_ORDERS):
    m = get_membership(request)
    require_feature(m.workspace, feature)
    return m


def m2(value):
    """Money as a string with 2 decimals (SQLite sums lose the scale)."""
    return f"{Decimal(value or 0):.2f}"


def _image_url(asset):
    return media_utils.preview_path(asset) if asset else ""


# ------------------------------------------------------------------ JSON shapes
def product_json(p):
    return {"id": p.id, "name": p.name, "sku": p.sku, "description": p.description, "price": str(p.price),
            "compare_at_price": str(p.compare_at_price) if p.compare_at_price is not None else None, "stock": p.stock,
            "variants": p.variants, "image_id": str(p.image_id) if p.image_id else None, "image_url": _image_url(p.image),
            "weight_kg": str(p.weight_kg), "active": p.active}


def customer_json(c, with_stats=True):
    data = {"id": str(c.id), "name": c.name, "phone": c.phone, "email": c.email, "address": c.address, "city": c.city,
            "district": c.district, "notes": c.notes, "created_at": c.created_at}
    if with_stats:
        agg = c.orders.exclude(status__in=["cancelled", "returned"]).aggregate(n=Count("id"), total=Sum("total"))
        data.update(orders_count=agg["n"] or 0, total_spent=m2(agg["total"]),
                    last_order_at=c.orders.order_by("-created_at").values_list("created_at", flat=True).first(),
                    contacts=[{"id": str(ct.id), "name": ct.name, "handle": ct.handle, "provider": ct.channel.provider,
                               "channel": ct.channel.name,
                               "conversation_id": str(ct.conversations.order_by("-last_message_at").values_list("id", flat=True).first() or "")}
                              for ct in c.contacts.select_related("channel")])
    return data


def order_json(o, full=True):
    data = {
        "id": str(o.id), "number": o.number, "status": o.status, "status_label": o.get_status_display(),
        "payment_method": o.payment_method, "payment_status": o.payment_status, "currency": o.currency,
        "subtotal": str(o.subtotal), "delivery_charge": str(o.delivery_charge), "discount": str(o.discount),
        "total": str(o.total), "recipient_name": o.recipient_name, "recipient_phone": o.recipient_phone,
        "address": o.address, "city": o.city, "district": o.district, "note": o.note,
        "courier": o.courier, "courier_name": o.courier_name, "tracking_id": o.tracking_id, "tracking_url": o.tracking_url,
        "delivery_status": o.delivery_status, "created_at": o.created_at, "paid_at": o.paid_at, "shipped_at": o.shipped_at,
        "delivered_at": o.delivered_at, "conversation_id": str(o.conversation_id) if o.conversation_id else None,
        "customer": {"id": str(o.customer_id), "name": o.customer.name} if o.customer_id else None,
        "items_count": sum(i.quantity for i in o.items.all()),
        "provider": o.conversation.channel.provider if o.conversation_id else None,
        "source": o.source,
    }
    if full:
        data["items"] = [{"id": i.id, "product_id": i.product_id, "name": i.name, "variant": i.variant, "quantity": i.quantity,
                          "unit_price": str(i.unit_price), "line_total": str(i.line_total),
                          "image_url": _image_url(i.product.image) if i.product_id and i.product and i.product.image_id else ""}
                         for i in o.items.select_related("product__image")]
        data["history"] = o.history
        data["payment_links"] = [{"id": str(l.id), "url": l.url, "amount": str(l.amount), "status": l.status,
                                  "gateway": l.gateway, "created_at": l.created_at} for l in o.payment_links.order_by("-created_at")]
        data["created_by"] = (o.created_by.get_full_name() or o.created_by.email) if o.created_by else ""
    return data


# ------------------------------------------------------------------ shop settings
class ShopIn(serializers.ModelSerializer):
    khalti_secret_key = serializers.CharField(required=False, allow_blank=True, write_only=True, max_length=200)
    esewa_secret_key = serializers.CharField(required=False, allow_blank=True, write_only=True, max_length=200)
    ncm_token = serializers.CharField(required=False, allow_blank=True, write_only=True, max_length=200)
    pathao = serializers.DictField(required=False, write_only=True)

    class Meta:
        model = ShopSettings
        fields = ["currency", "order_prefix", "delivery_inside_valley", "delivery_outside_valley", "bank_details",
                  "khalti_live", "esewa_live", "esewa_merchant_code", "ncm_live", "ncm_from_branch", "pathao_base_url",
                  "pathao_store_id", "msg_order_summary", "msg_paid", "msg_shipped", "msg_delivered",
                  "auto_message_paid", "auto_message_shipped", "auto_message_delivered",
                  "msg_out_for_delivery", "auto_message_out_for_delivery", "auto_ship", "default_courier",
                  "payment_receivers", "khalti_secret_key", "esewa_secret_key", "ncm_token", "pathao"]

    def validate_default_courier(self, value):
        if value not in ("", "ncm", "pathao"):
            raise serializers.ValidationError("Choose Nepal Can Move or Pathao.")
        return value

    def validate(self, attrs):
        auto = attrs.get("auto_ship", getattr(self.instance, "auto_ship", "off"))
        courier = attrs.get("default_courier", getattr(self.instance, "default_courier", ""))
        if auto != "off" and not courier:
            raise serializers.ValidationError({"default_courier": ["Pick the courier to book automatically."]})
        return attrs

    def validate_pathao_base_url(self, value):
        if value and not value.startswith("https://"):
            raise serializers.ValidationError("Use an https:// address.")
        return value

    def update(self, instance, data):
        secrets = dict(instance.secrets or {})
        for key in SECRET_FIELDS:
            if key in data:
                value = data.pop(key).strip()
                if value:  # empty = keep the saved value
                    secrets[key] = value
        if "pathao" in data:
            incoming = {k: str(v).strip() for k, v in data.pop("pathao").items()
                        if k in ("client_id", "client_secret", "username", "password") and str(v).strip()}
            if incoming:
                secrets["pathao"] = {**secrets.get("pathao", {}), **incoming, "access_token": "", "refresh_token": ""}
        instance.secrets = secrets
        return super().update(instance, data)


def shop_json(shop):
    ser = ShopIn(shop).data
    s = shop.secrets or {}
    p = s.get("pathao", {})
    return {**ser,
            "configured": {"khalti": bool(s.get("khalti_secret_key")), "esewa": bool(shop.esewa_merchant_code and s.get("esewa_secret_key")),
                           "ncm": bool(s.get("ncm_token")), "pathao": bool(p.get("client_id") and p.get("username"))},
            "gateways": list(payments.gateways(shop)), "couriers": list(delivery.couriers(shop)),
            "features": {"orders": shop.workspace.has_feature(F_ORDERS), "couriers": shop.workspace.has_feature(F_COURIERS)}}


class ShopSettingsView(APIView):
    def get(self, request):
        return Response(shop_json(ShopSettings.for_workspace(get_membership(request).workspace)))

    def put(self, request):
        m = require(request, "manage_shop")
        shop = ShopSettings.for_workspace(m.workspace)
        ser = ShopIn(shop, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        changed = sorted(k for k in request.data if k in ShopIn.Meta.fields)
        ser.save()
        audit(request, "payments.settings_changed", meta={"fields": changed})
        return Response(shop_json(shop))


class CourierLookupView(APIView):
    """GET shop/couriers/ncm/branches/ · pathao/cities/ · pathao/zones/?city= · pathao/areas/?zone="""

    def get(self, request, courier, what):
        m = _ws(request, F_COURIERS)
        shop = ShopSettings.for_workspace(m.workspace)
        c = delivery.couriers(shop).get(courier)
        if c is None:
            return Response({"detail": "Connect this courier first in Settings → Shop."}, status=400)
        try:
            if courier == "ncm" and what == "branches":
                return Response(c.branches())
            if courier == "pathao" and what == "cities":
                return Response(c.cities())
            if courier == "pathao" and what == "zones":
                return Response(c.zones(request.query_params.get("city", 0)))
            if courier == "pathao" and what == "areas":
                return Response(c.areas(request.query_params.get("zone", 0)))
        except (delivery.DeliveryError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response({"detail": "Unknown lookup."}, status=404)


# ------------------------------------------------------------------ products
class ProductIn(serializers.ModelSerializer):
    image_id = serializers.UUIDField(required=False, allow_null=True)

    class Meta:
        model = Product
        fields = ["name", "sku", "description", "price", "compare_at_price", "stock", "variants", "image_id", "weight_kg", "active"]

    def validate_variants(self, value):
        if not isinstance(value, list) or len(value) > 50:
            raise serializers.ValidationError("Up to 50 options.")
        return [str(v).strip()[:60] for v in value if str(v).strip()]

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Price can't be negative.")
        return value

    def validate_image_id(self, value):
        if value and not MediaAsset.objects.filter(id=value, workspace=self.context["workspace"], kind="image").exists():
            raise serializers.ValidationError("Unknown image.")
        return value


class ProductsView(APIView):
    def get(self, request):
        m = _ws(request)
        qs = Product.objects.filter(workspace=m.workspace).select_related("image")
        q = request.query_params.get("q", "").strip()[:100]
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q))
        if request.query_params.get("active") == "1":
            qs = qs.filter(active=True)
        return Response([product_json(p) for p in qs[:500]])

    def post(self, request):
        m = _ws(request)
        require(request, "manage_products")
        ser = ProductIn(data=request.data, context={"workspace": m.workspace})
        ser.is_valid(raise_exception=True)
        p = ser.save(workspace=m.workspace)
        return Response(product_json(p), status=201)


class ProductDetailView(APIView):
    def put(self, request, pk):
        m = _ws(request)
        require(request, "manage_products")
        p = get_object_or_404(Product, workspace=m.workspace, pk=pk)
        ser = ProductIn(p, data=request.data, partial=True, context={"workspace": m.workspace})
        ser.is_valid(raise_exception=True)
        return Response(product_json(ser.save()))

    def delete(self, request, pk):
        m = _ws(request)
        require(request, "manage_products")
        get_object_or_404(Product, workspace=m.workspace, pk=pk).delete()
        return Response(status=204)


class ProductImageView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        m = _ws(request)
        require(request, "manage_products")
        f = request.FILES.get("file")
        if f is None:
            return Response({"file": ["Choose an image."]}, status=400)
        head = f.read(16)
        f.seek(0)
        mime = media_utils.sniff(head)
        if mime not in media_utils.IMAGE_TYPES:
            return Response({"file": ["Upload a JPEG or PNG image."]}, status=400)
        if f.size > media_utils.MAX_IMAGE:
            return Response({"file": ["Image too large (max 8 MB)."]}, status=400)
        asset = MediaAsset(workspace=m.workspace, kind="image", mime=mime, size=f.size, original_name=f.name[:255],
                           uploaded_by=request.user)
        asset.file.save(f"product.{media_utils.IMAGE_TYPES[mime]}", f, save=False)
        asset.save()
        return Response({"id": str(asset.id), "url": media_utils.preview_path(asset)}, status=201)


# ------------------------------------------------------------------ customers
class CustomerIn(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["name", "phone", "email", "address", "city", "district", "notes"]

    def validate_phone(self, value):
        return services.normalize_phone(value) if value else ""


class CustomersView(APIView):
    def get(self, request):
        m = _ws(request)
        qs = Customer.objects.filter(workspace=m.workspace)
        q = request.query_params.get("q", "").strip()[:100]
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(email__icontains=q) | Q(city__icontains=q)
                           | Q(contacts__handle__icontains=q)).distinct()
        qs = qs.annotate(n=Count("orders", filter=~Q(orders__status__in=["cancelled", "returned"]), distinct=True),
                         spent=Sum("orders__total", filter=~Q(orders__status__in=["cancelled", "returned"])))
        rows = []
        for c in qs.prefetch_related("contacts__channel")[:300]:
            rows.append({**customer_json(c, with_stats=False), "orders_count": c.n, "total_spent": m2(c.spent),
                         "providers": sorted({ct.channel.provider for ct in c.contacts.all()})})
        return Response(rows)

    def post(self, request):
        m = _ws(request)
        ser = CustomerIn(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(customer_json(ser.save(workspace=m.workspace)), status=201)


class CustomerDetailView(APIView):
    def _get(self, request, pk):
        m = _ws(request)
        return m, get_object_or_404(Customer, workspace=m.workspace, pk=pk)

    def get(self, request, pk):
        _, c = self._get(request, pk)
        return Response({**customer_json(c), "orders": [order_json(o, full=False) for o in c.orders.select_related(
            "conversation__channel", "customer").prefetch_related("items")[:100]]})

    def put(self, request, pk):
        _, c = self._get(request, pk)
        ser = CustomerIn(c, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        return Response(customer_json(ser.save()))

    def delete(self, request, pk):
        require(request, "manage_products")
        _, c = self._get(request, pk)
        c.delete()
        return Response(status=204)


class CustomerMergeView(APIView):
    def post(self, request, pk):
        m = _ws(request)
        keep = get_object_or_404(Customer, workspace=m.workspace, pk=pk)
        other = get_object_or_404(Customer, workspace=m.workspace, pk=request.data.get("other_id"))
        if keep.pk == other.pk:
            return Response({"detail": "Pick a different customer."}, status=400)
        return Response(customer_json(services.merge_customers(keep, other)))


class ConversationCustomerView(APIView):
    """The customer behind a conversation (created on first use) + their orders. Used by the inbox side panel."""

    def _conv(self, request, conversation_id):
        m = _ws(request)
        qs = visible_conversations(request, Conversation.objects.filter(workspace=m.workspace))
        return get_object_or_404(qs.select_related("contact__customer", "channel"), id=conversation_id)

    def get(self, request, conversation_id):
        conv = self._conv(request, conversation_id)
        cust = conv.contact.customer
        if cust is None:
            return Response({"customer": None, "orders": [], "suggested": _suggest(conv)})
        return Response({"customer": customer_json(cust), "orders": [order_json(o, full=False) for o in cust.orders.select_related(
            "conversation__channel", "customer").prefetch_related("items")[:20]], "suggested": None})

    def put(self, request, conversation_id):
        conv = self._conv(request, conversation_id)
        ser = CustomerIn(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        cust = services.customer_for_contact(conv.contact, **ser.validated_data)
        for key in ("email", "notes"):
            if key in ser.validated_data:
                setattr(cust, key, ser.validated_data[key])
        cust.save()
        return self.get(request, conversation_id)


def _suggest(conv):
    """Prefill from the contact (a phone number handle from WhatsApp/Viber)."""
    phone = services.normalize_phone(conv.contact.handle)
    return {"name": conv.contact.name, "phone": phone if len(phone) >= 10 else ""}


# ------------------------------------------------------------------ orders
class ItemIn(serializers.Serializer):
    product_id = serializers.IntegerField(required=False, allow_null=True)
    name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    variant = serializers.CharField(required=False, allow_blank=True, max_length=100)
    quantity = serializers.IntegerField(min_value=1, max_value=10000, default=1)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=Decimal("0"))

    def validate(self, data):
        if not data.get("product_id") and not (data.get("name") or "").strip():
            raise serializers.ValidationError("Each item needs a product or a name.")
        if not data.get("product_id") and data.get("unit_price") is None:
            raise serializers.ValidationError("Custom items need a price.")
        return data


class OrderIn(serializers.Serializer):
    conversation_id = serializers.UUIDField(required=False, allow_null=True)
    customer_id = serializers.UUIDField(required=False, allow_null=True)
    items = ItemIn(many=True, required=False)
    payment_method = serializers.ChoiceField(choices=[c for c, _ in Order.PAYMENT_METHODS], required=False)
    delivery_charge = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, min_value=Decimal("0"))
    discount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, min_value=Decimal("0"))
    recipient_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    recipient_phone = serializers.CharField(required=False, allow_blank=True, max_length=30)
    address = serializers.CharField(required=False, allow_blank=True, max_length=300)
    city = serializers.CharField(required=False, allow_blank=True, max_length=100)
    district = serializers.CharField(required=False, allow_blank=True, max_length=100)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def to_data(self, request, ws):
        d = dict(self.validated_data)
        if "conversation_id" in d:
            cid = d.pop("conversation_id")
            d["conversation"] = (visible_conversations(request, Conversation.objects.filter(workspace=ws))
                                 .filter(id=cid).first() if cid else None)
            if cid and d["conversation"] is None:
                raise serializers.ValidationError({"conversation_id": "Unknown conversation."})
        if "customer_id" in d:
            cid = d.pop("customer_id")
            d["customer"] = Customer.objects.filter(workspace=ws, id=cid).first() if cid else None
        if "items" in d:
            d["items"] = [dict(i) for i in d["items"]]
        return d


class OrdersView(APIView):
    def get(self, request):
        m = _ws(request)
        qs = Order.objects.filter(workspace=m.workspace).select_related("customer", "conversation__channel").prefetch_related("items")
        p = request.query_params
        if p.get("status") and p["status"] != "all":
            qs = qs.filter(status__in=p["status"].split(","))
        if p.get("payment_status"):
            qs = qs.filter(payment_status=p["payment_status"])
        if p.get("conversation"):
            qs = qs.filter(conversation_id=p["conversation"])
        if p.get("customer"):
            qs = qs.filter(customer_id=p["customer"])
        q = p.get("q", "").strip()[:100]
        if q:
            qs = qs.filter(Q(number__icontains=q) | Q(recipient_name__icontains=q) | Q(recipient_phone__icontains=q)
                           | Q(tracking_id__icontains=q))
        return Response([order_json(o, full=False) for o in qs[:300]])

    def post(self, request):
        m = _ws(request)
        ser = OrderIn(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.to_data(request, m.workspace)
        if not data.get("items"):
            return Response({"items": ["Add at least one item."]}, status=400)
        if "delivery_charge" not in data:
            shop = ShopSettings.for_workspace(m.workspace)
            valley = (data.get("district") or data.get("city") or "").lower()
            inside = any(w in valley for w in ("kathmandu", "lalitpur", "bhaktapur", "patan"))
            data["delivery_charge"] = shop.delivery_inside_valley if inside or not valley else shop.delivery_outside_valley
        order = services.save_order(m.workspace, data, user=request.user)
        return Response(order_json(order), status=201)


class OrderStatsView(APIView):
    def get(self, request):
        m = _ws(request)
        qs = Order.objects.filter(workspace=m.workspace)
        month = timezone.localdate().replace(day=1)
        by_status = dict(qs.values_list("status").annotate(n=Count("id")).order_by())
        revenue = qs.filter(created_at__date__gte=month).exclude(status__in=["cancelled", "returned"]).aggregate(
            t=Sum("total"), n=Count("id"))
        paid = qs.filter(paid_at__date__gte=month).aggregate(t=Sum("total"))
        return Response({"by_status": by_status, "month_orders": revenue["n"] or 0, "month_revenue": m2(revenue["t"]),
                         "month_collected": m2(paid["t"]), "unpaid": qs.exclude(status__in=["cancelled", "returned"])
                         .exclude(payment_status="paid").count()})


class OrderDetailView(APIView):
    def _get(self, request, pk):
        m = _ws(request)
        return m, get_object_or_404(Order.objects.select_related("customer", "conversation__channel", "conversation__contact"),
                                    workspace=m.workspace, pk=pk)

    def get(self, request, pk):
        return Response(order_json(self._get(request, pk)[1]))

    def put(self, request, pk):
        m, order = self._get(request, pk)
        if order.status in ("shipped", "delivered", "cancelled", "returned") and "items" in request.data:
            return Response({"detail": "Items can't be changed after the order has shipped."}, status=400)
        ser = OrderIn(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        order = services.save_order(m.workspace, ser.to_data(request, m.workspace), user=request.user, order=order)
        return Response(order_json(order))


class OrderActionView(APIView):
    """POST orders/<id>/<action>/: status · payment-link · mark-paid · ship · send-summary."""

    throttle_scope = "send"

    def post(self, request, pk, action):
        m = _ws(request, F_COURIERS if action == "ship" and request.data.get("courier") in ("ncm", "pathao") else F_ORDERS)
        order = get_object_or_404(Order.objects.select_related("conversation__channel", "customer"), workspace=m.workspace, pk=pk)
        shop = ShopSettings.for_workspace(m.workspace)
        if action == "status":
            new = request.data.get("status")
            if new not in dict(Order.STATUSES):
                return Response({"status": ["Unknown status."]}, status=400)
            services.set_status(order, new, request.user, notify=bool(request.data.get("notify", True)))
            audit(request, "order.status", target=order.number, meta={"status": new})
        elif action == "payment-link":
            if not payments.gateways(shop):
                return Response({"detail": "Connect Khalti or eSewa first in Settings → Shop → Payments."}, status=400)
            if order.payment_status == "paid":
                return Response({"detail": "This order is already paid."}, status=400)
            link = services.create_payment_link(order)
            if request.data.get("send") and order.conversation_id:
                msg = services.message_customer(order, f"Here is your secure payment link for order {order.number} "
                                                       f"({services.money(order.total, order.currency)}): {link.url}", request.user)
                if msg is not None and msg.status == "failed":
                    return Response({"detail": f"Link created but the message failed: {msg.error[:200]}", "url": link.url}, status=502)
        elif action == "mark-paid":
            services.mark_paid(order, via=str(request.data.get("via") or order.get_payment_method_display())[:40], user=request.user)
        elif action == "ship":
            try:
                services.ship(order, str(request.data.get("courier") or "manual"), request.data, request.user)
            except delivery.DeliveryError as exc:
                return Response({"detail": str(exc)}, status=502)
        elif action == "send-summary":
            if not order.conversation_id:
                return Response({"detail": "This order isn't linked to a conversation."}, status=400)
            link = None
            if order.payment_method in ("khalti", "esewa") and order.payment_status != "paid" and payments.gateways(shop):
                link = services.create_payment_link(order)
            text = services.render(shop.msg_order_summary, order, payment=services.payment_line(order, link))
            msg = services.message_customer(order, text, request.user)
            if msg is not None and msg.status == "failed":
                return Response({"detail": f"Couldn't send: {msg.error[:200]}"}, status=502)
            services.log(order, "Order summary sent to the customer", request.user)
            order.save(update_fields=["history", "updated_at"])
        else:
            return Response({"detail": "Unknown action."}, status=404)
        order.refresh_from_db()
        return Response(order_json(order))


# ------------------------------------------------------------------ public payment page
class PublicPayView(APIView):
    """GET pay/<id>/: what the customer sees on the payment page (no login)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, link_id):
        link = get_object_or_404(PaymentLink.objects.select_related("order__workspace"), id=link_id,
                                 order__workspace__suspended_at__isnull=True)
        o = link.order
        shop = ShopSettings.for_workspace(o.workspace)
        return Response({
            "shop": o.workspace.name, "order": o.number, "amount": str(link.amount), "currency": o.currency,
            "status": "paid" if o.payment_status == "paid" else link.status,
            "items": [{"name": i.name, "variant": i.variant, "quantity": i.quantity, "line_total": str(i.line_total)}
                      for i in o.items.all()],
            "delivery_charge": str(o.delivery_charge), "discount": str(o.discount),
            "gateways": list(payments.gateways(shop)) if link.status == "pending" and o.payment_status != "paid" else [],
            "test_mode": {"khalti": not shop.khalti_live, "esewa": not shop.esewa_live},
            "brand": _public_brand(o.workspace),
        })


def _public_brand(ws):
    from core.serializers import WorkspaceSerializer
    return WorkspaceSerializer(ws).data["brand"]


class PublicPayStartView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "auth"

    def post(self, request, link_id, gateway):
        link = get_object_or_404(PaymentLink.objects.select_related("order__workspace"), id=link_id,
                                 order__workspace__suspended_at__isnull=True)
        if link.status != "pending" or link.order.payment_status == "paid":
            return Response({"detail": "This link has already been used."}, status=400)
        if link.amount != link.order.total:
            return Response({"detail": "The order total changed. Ask the shop for a new link."}, status=400)
        g = payments.gateways(ShopSettings.for_workspace(link.order.workspace)).get(gateway)
        if g is None:
            return Response({"detail": "This payment method isn't available."}, status=400)
        try:
            return Response(g.start(link))
        except payments.PaymentError as exc:
            return Response({"detail": str(exc)}, status=502)


def pay_return(request, link_id, gateway, failed=False):
    """The customer's browser lands here after paying; we verify with the gateway before marking anything paid."""
    target = f"{settings.FRONTEND_URL}/pay/{link_id}"
    link = PaymentLink.objects.select_related("order__workspace").filter(
        id=link_id, gateway=gateway, order__workspace__suspended_at__isnull=True).first()
    if link is None:
        return HttpResponseRedirect(f"{target}?result=failed")
    if link.status == "paid":
        return HttpResponseRedirect(f"{target}?result=success")
    g = payments.gateways(ShopSettings.for_workspace(link.order.workspace)).get(gateway)
    params = request.GET.dict()
    if failed:
        params["failed"] = "1"
    try:
        ok, txn, raw = g.verify(link, params) if g else (False, "", {"error": "gateway disabled"})
    except Exception as exc:  # noqa: BLE001
        logger.exception("Payment link verification failed")
        ok, txn, raw = False, "", {"error": str(exc)[:200]}
    if ok:
        link.status, link.txn_id, link.raw, link.paid_at = "paid", txn, raw, timezone.now()
        link.save()
        services.mark_paid(link.order, via=gateway.title() if gateway != "esewa" else "eSewa", txn=txn)
        return HttpResponseRedirect(f"{target}?result=success")
    link.raw = raw
    link.save(update_fields=["raw"])
    return HttpResponseRedirect(f"{target}?result=failed")


__all__ = ["status"]


# ------------------------------------------------------------------ payment screenshots
class PaymentChecksView(APIView):
    """GET payment-checks/?conversation=<id>&status=pending"""

    def get(self, request):
        m = _ws(request)
        qs = PaymentCheck.objects.filter(workspace=m.workspace).select_related("order", "attachment", "reviewed_by")
        conv_id = request.query_params.get("conversation")
        if conv_id:
            conv = get_object_or_404(visible_conversations(request, Conversation.objects.filter(workspace=m.workspace)), id=conv_id)
            qs = qs.filter(conversation=conv)
        else:
            qs = qs.filter(conversation__in=visible_conversations(request, Conversation.objects.filter(workspace=m.workspace)))
        if request.query_params.get("status") in dict(PaymentCheck.STATUSES):
            qs = qs.filter(status=request.query_params["status"])
        return Response([payment_check.check_json(c) for c in qs[:100]])


class PaymentCheckActionView(APIView):
    """POST payment-checks/<id>/confirm/ {order_id?} · reject/ {message?}"""

    throttle_scope = "send"

    def post(self, request, pk, action):
        m = _ws(request)
        check = get_object_or_404(PaymentCheck.objects.filter(
            conversation__in=visible_conversations(request, Conversation.objects.filter(workspace=m.workspace))), pk=pk)
        if check.status != PaymentCheck.PENDING:
            return Response({"detail": "This screenshot was already reviewed."}, status=400)
        if action == "confirm":
            order = None
            if request.data.get("order_id"):
                order = get_object_or_404(Order, workspace=m.workspace, pk=request.data["order_id"])
            try:
                check = payment_check.confirm(check, request.user, order)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=400)
            audit(request, "payment.screenshot_confirmed", target=check.order.number if check.order else "",
                  meta={"txn": check.txn_id, "verdict": check.verdict})
        elif action == "reject":
            payment_check.reject(check, request.user, str(request.data.get("message") or ""))
            audit(request, "payment.screenshot_rejected", meta={"txn": check.txn_id, "verdict": check.verdict})
        else:
            return Response({"detail": "Unknown action."}, status=404)
        check.refresh_from_db()
        return Response(payment_check.check_json(check))


# ------------------------------------------------------------------ visits / appointments
def booking_json(b):
    return {"id": str(b.id), "name": b.name, "phone": b.phone, "purpose": b.purpose, "starts_at": b.starts_at,
            "minutes": b.minutes, "status": b.status, "status_label": b.get_status_display(), "note": b.note,
            "source": b.source, "created_at": b.created_at,
            "conversation_id": str(b.conversation_id) if b.conversation_id else None,
            "provider": b.conversation.channel.provider if b.conversation_id else None,
            "customer_id": str(b.customer_id) if b.customer_id else None}


class BookingIn(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ["name", "phone", "purpose", "starts_at", "minutes", "status", "note"]
        extra_kwargs = {"minutes": {"min_value": 5, "max_value": 480}}

    def validate_phone(self, value):
        return services.normalize_phone(value) or value


class BookingsView(APIView):
    """GET bookings/?from=&to=&status= · POST (add a visit by hand)"""

    def get(self, request):
        from datetime import datetime, timedelta
        ws = get_membership(request).workspace
        qs = Booking.objects.filter(workspace=ws).select_related("conversation__channel")
        start = request.query_params.get("from")
        end = request.query_params.get("to")
        try:
            start = datetime.fromisoformat(start) if start else timezone.now() - timedelta(days=1)
            end = datetime.fromisoformat(end) if end else start + timedelta(days=60)
        except ValueError:
            return Response({"detail": "Use ISO dates for from / to."}, status=400)
        if timezone.is_naive(start):
            start = timezone.make_aware(start)
        if timezone.is_naive(end):
            end = timezone.make_aware(end)
        qs = qs.filter(starts_at__gte=start, starts_at__lt=end)
        if request.query_params.get("status") in dict(Booking.STATUSES):
            qs = qs.filter(status=request.query_params["status"])
        return Response([booking_json(b) for b in qs[:500]])

    def post(self, request):
        m = get_membership(request)
        ser = BookingIn(data=request.data)
        ser.is_valid(raise_exception=True)
        b = ser.save(workspace=m.workspace, created_by=request.user, source="manual")
        return Response(booking_json(b), status=201)


class BookingDetailView(APIView):
    def _get(self, request, pk):
        return get_object_or_404(Booking.objects.select_related("conversation__channel"),
                                 workspace=get_membership(request).workspace, pk=pk)

    def patch(self, request, pk):
        b = self._get(request, pk)
        ser = BookingIn(b, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        b = ser.save()
        if request.data.get("notify") and b.conversation_id and ("starts_at" in request.data or request.data.get("status") == "cancelled"):
            from automations.models import AssistantSettings
            cfg = AssistantSettings.for_workspace(b.workspace)
            from zoneinfo import ZoneInfo
            local = b.starts_at.astimezone(ZoneInfo(cfg.timezone))
            text = (f"Your {cfg.booking_label.lower()} has been cancelled. Reply here if you'd like a new time."
                    if b.status == "cancelled" else
                    f"Your {cfg.booking_label.lower()} is now on {local:%A, %d %B} at {local:%I:%M %p}. See you then!")
            from inbox.services import send_reply
            send_reply(b.conversation, text, user=request.user)
        return Response(booking_json(b))

    def delete(self, request, pk):
        self._get(request, pk).delete()
        return Response(status=204)
