"""
    This module contains the models required for implimenting the shopping cart
"""
import logging
import uuid
from copy import copy
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from parkpasses.components.cart.utils import CartUtils
from parkpasses.components.concessions.models import ConcessionUsage
from parkpasses.components.discount_codes.models import DiscountCodeUsage
from parkpasses.components.orders.models import Order, OrderItem
from parkpasses.components.passes.models import Pass
from parkpasses.components.vouchers.models import Voucher, VoucherTransaction
from parkpasses.ledger_api_utils import retrieve_email_user

logger = logging.getLogger(__name__)


class CartManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().prefetch_related("items")


class Cart(models.Model):
    """A class to represent a cart"""

    user = models.IntegerField(null=True, blank=True)  # EmailUserRO
    datetime_created = models.DateTimeField(auto_now_add=True, null=False, blank=False)
    uuid = models.CharField(max_length=36, blank=True, null=True)
    datetime_first_added_to = models.DateTimeField(null=True, blank=True)
    datetime_last_added_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "parkpasses"

    def __str__(self):
        return f"Cart for user: {self.user} (Created: {self.datetime_created})"

    @classmethod
    def get_or_create_cart(self, request):
        cart_id = request.session.get("cart_id", None)
        if cart_id and Cart.objects.filter(id=cart_id).exists():
            cart = Cart.objects.get(id=cart_id)
            # There is an edge case here where a user has a cart in db but is browsing the site
            # annonymously and adds one or more items to their cart. When they log in we need to move
            # the items from their anonymous cart to their already existing cart...
            if Cart.objects.filter(user=request.user.id).exclude(id=cart.id).exists():
                anon_cart = copy(cart)
                cart = (
                    Cart.objects.filter(user=request.user.id)
                    .exclude(id=cart.id)
                    .order_by("user", "-datetime_created")
                    .first()
                )
                if anon_cart.items.all().exists():
                    anon_cart.items.all().update(cart=cart)
                    anon_cart.delete()
            else:
                if not cart.user:
                    cart.user = request.user.id
                    cart.save()
        else:
            if Cart.objects.filter(user=request.user.id).exists():
                cart = (
                    Cart.objects.filter(user=request.user.id)
                    .order_by("user", "-datetime_created")
                    .first()
                )
            else:
                cart = Cart.objects.create()
        request.session["cart_item_count"] = CartItem.objects.filter(cart=cart).count()
        request.session["cart_id"] = cart.id
        return cart

    def set_user_for_cart_and_items(self, user_id):
        self.user = user_id
        self.save()
        logger.debug("Selecting vouchers")

        voucher_ids = list(CartItem.vouchers.filter(cart=self))
        vouchers = Voucher.objects.filter(id__in=voucher_ids)
        for voucher in vouchers:
            voucher.purchaser = user_id
            voucher.save()

        park_pass_ids = list(CartItem.passes.filter(cart=self))
        park_passes = Pass.objects.filter(id__in=park_pass_ids)
        for park_pass in park_passes:
            park_pass.purchaser = user_id
            park_pass.save()

    @property
    def email_user(self):
        return retrieve_email_user(self.user)

    @property
    def grand_total(self):
        grand_total = 0.00
        for item in self.items.all():
            grand_total += float(item.get_total_price())
        return grand_total

    def create_order(
        self, save_order_to_db_and_delete_cart=False, uuid=None, invoice_reference=None
    ):
        """This method can create an order and order items from a cart (and cart items)
        By default it doesn't add this order to the database. This is so we can use the
        order to submit to leger and wait until that order is confirmed before we add
        the order to the park passes database.
        """
        logger.debug("create_order running")
        logger.debug(
            "save_order_to_db_and_delete_cart = "
            + str(save_order_to_db_and_delete_cart)
        )
        order = Order(user=self.user)
        order_items = []
        if save_order_to_db_and_delete_cart:
            order.uuid = uuid
            order.invoice_reference = invoice_reference
            order.save()
        for cart_item in self.items.all():
            order_item = OrderItem()
            order_item.object_id = cart_item.object_id
            order_item.content_type_id = cart_item.content_type_id
            order_item.order = order
            if cart_item.is_voucher_purchase():
                voucher = Voucher.objects.get(pk=cart_item.object_id)
                order_item.description = CartUtils.get_voucher_purchase_description(
                    voucher.voucher_number
                )
                order_item.amount = voucher.amount
                order_items.append(order_item)
                if save_order_to_db_and_delete_cart:
                    voucher.in_cart = False
                    voucher.save()
                    order_item.save()
            else:
                park_pass = Pass.objects.get(pk=cart_item.object_id)
                order_item.description = CartUtils.get_pass_purchase_description(
                    park_pass.pass_number
                )
                order_item.amount = park_pass.option.price
                order_items.append(order_item)
                if save_order_to_db_and_delete_cart:
                    park_pass.in_cart = False
                    park_pass.save()
                    order_item.save()

                if cart_item.concession_usage:
                    # A conession discount is being applied to this pass purchase
                    concession = cart_item.concession_usage.concession
                    concession_discount = concession.discount_as_amount(
                        park_pass.option.price
                    )
                    if concession_discount > Decimal(0.00):
                        order_item = OrderItem()
                        order_item.order = order
                        order_item.description = CartUtils.get_concession_description(
                            concession.concession_type
                        )
                        # The ledger checkout doesn't round a negative balance to zero so in order to avoid
                        # processing a refund we have to make sure the discount is no more than the total pass price
                        if concession_discount >= park_pass.price:
                            order_item.amount = -abs(
                                park_pass.price.quantize(Decimal("0.01"))
                            )
                        else:
                            order_item.amount = -abs(
                                concession_discount.quantize(Decimal("0.01"))
                            )
                        order_items.append(order_item)
                        if save_order_to_db_and_delete_cart:
                            order_item.save()

                if cart_item.discount_code_usage:
                    # A discount code is being applied to this pass purchase
                    discount_code_discount = (
                        cart_item.get_discount_code_discount_as_amount()
                    )
                    if discount_code_discount > 0.00:
                        order_item = OrderItem()
                        order_item.order = order
                        order_item.description = (
                            CartUtils.get_discount_code_description(
                                cart_item.discount_code.code
                            )
                        )
                        # The ledger checkout doesn't round a negative balance to zero so in order to avoid
                        # processing a refund we have to make sure the discount is no more than the total pass price
                        if discount_code_discount >= park_pass.price:
                            order_item.amount = -abs(
                                park_pass.price.quantize(Decimal("0.01"))
                            )
                        else:
                            order_item.amount = -abs(
                                discount_code_discount.quantize(Decimal("0.01"))
                            )
                        order_items.append(order_item)
                        if save_order_to_db_and_delete_cart:
                            order_item.save()

                if cart_item.voucher_transaction:
                    # A voucher is being used for this pass purchase
                    voucher = cart_item.voucher_transaction.voucher
                    voucher_discount = cart_item.get_voucher_discount_as_amount()
                    if 0.00 < voucher_discount:
                        order_item = OrderItem()
                        order_item.order = order
                        order_item.description = CartUtils.get_voucher_code_description(
                            cart_item.voucher.code
                        )
                        order_item.amount = -abs(
                            voucher_discount.quantize(Decimal("0.01"))
                        )
                        order_item.amount = -abs(voucher_discount)
                        order_items.append(order_item)
                        if save_order_to_db_and_delete_cart:
                            order_item.save()

        if save_order_to_db_and_delete_cart:
            self.delete()

        return order, order_items

    def save(self, *args, **kwargs):
        if not self.uuid:
            self.uuid = uuid.uuid4()
        super().save(*args, **kwargs)


class CartItemVoucherManager(models.Manager):
    def get_queryset(self):
        content_type = ContentType.objects.get_for_model(Voucher)
        return (
            super()
            .get_queryset()
            .filter(content_type=content_type)
            .values_list("object_id", flat=True)
        )


class CartItemPassManager(models.Manager):
    def get_queryset(self):
        content_type = ContentType.objects.get_for_model(Pass)
        return (
            super()
            .get_queryset()
            .filter(content_type=content_type)
            .values_list("object_id", flat=True)
        )


class CartItemManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("cart")


class CartItem(models.Model):
    """A class to represent a cart item"""

    objects = CartItemManager()

    vouchers = CartItemVoucherManager()

    passes = CartItemPassManager()

    cart = models.ForeignKey(
        Cart, related_name="items", on_delete=models.CASCADE, null=False, blank=False
    )
    object_id = models.CharField(max_length=191)  # voucher or pass id
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE
    )  # Voucher or Pass
    concession_usage = models.ForeignKey(
        ConcessionUsage, on_delete=models.PROTECT, null=True, blank=True
    )
    discount_code_usage = models.ForeignKey(
        DiscountCodeUsage, on_delete=models.PROTECT, null=True, blank=True
    )
    voucher_transaction = models.ForeignKey(
        VoucherTransaction, on_delete=models.PROTECT, null=True, blank=True
    )

    class Meta:
        app_label = "parkpasses"
        unique_together = (("content_type", "object_id"),)
        indexes = (models.Index(fields=["content_type", "object_id"]),)

    def __str__(self):
        return f"Content Type: {self.content_type} | Object ID: {self.object_id} Total Price: {self.get_total_price()}"

    def save(self, *args, **kwargs):
        logger.debug(
            "PARKPASSES_VALID_CART_CONTENT_TYPES = "
            + str(settings.PARKPASSES_VALID_CART_CONTENT_TYPES)
        )
        logger.debug("self.content_type = " + str(self.content_type))
        if str(self.content_type) not in settings.PARKPASSES_VALID_CART_CONTENT_TYPES:
            logger.error(
                f"Attempting to add invalid content type {self.content_type} \
                    to cart {self.cart.pk} for user {self.cart.user}"
            )
            raise ValueError("A Cart Item can only contain a Voucher or a Pass")
        datetime_item_added = timezone.now()
        if not self.cart.datetime_first_added_to and not self.cart.items.count():
            self.cart.datetime_first_added_to = datetime_item_added
        self.cart.datetime_last_added_to = datetime_item_added
        self.cart.save()
        super().save(*args, **kwargs)

    def is_voucher_purchase(self):
        return "parkpasses | voucher" == str(self.content_type)

    def is_pass_purchase(self):
        return "parkpasses | pass" == str(self.content_type)

    def delete(self, *args, **kwargs):
        if self.is_voucher_purchase():
            Voucher.objects.filter(id=self.object_id).delete()
        elif self.is_pass_purchase():
            if Pass.objects.filter(id=self.object_id).exists():
                park_pass = Pass.objects.get(id=self.object_id)
                self.concession_usage = None
                self.discount_code_usage = None
                self.voucher_transaction = None
                self.save()
                ConcessionUsage.objects.filter(park_pass=park_pass).delete()
                DiscountCodeUsage.objects.filter(park_pass=park_pass).delete()
                VoucherTransaction.objects.filter(park_pass=park_pass).delete()
                park_pass.delete()
        return super().delete(*args, **kwargs)

    def get_price_before_discounts(self):
        """Does not take concession, discount code and voucher into consideration"""
        model_type = str(self.content_type)
        logger.debug("model_type = " + str(model_type))
        if "parkpasses | voucher" == model_type:
            return Voucher.objects.get(pk=self.object_id).amount
        elif "parkpasses | pass" == model_type:
            return Pass.objects.get(pk=self.object_id).option.price

    def get_concession_price(self):
        model_type = str(self.content_type)
        if "parkpasses | voucher" == model_type:
            return Voucher.objects.get(pk=self.object_id).amount
        elif "parkpasses | pass" == model_type:
            park_pass = Pass.objects.get(pk=self.object_id)
            return park_pass.price_after_concession_applied

    def get_total_price(self):
        """Takes concession, discount code and voucher into consideration"""
        model_type = str(self.content_type)
        logger.debug("model_type = " + str(model_type))
        if "parkpasses | voucher" == model_type:
            return Voucher.objects.get(pk=self.object_id).amount
        elif "parkpasses | pass" == model_type:
            park_pass = Pass.objects.get(pk=self.object_id)
            return Decimal(park_pass.price_after_all_discounts)

    # TODO: DRY These should not be in this file. Move them to their respetive objects
    # then use this as convenience methods that just call those methods on the other objects
    def get_concession_discount_as_amount(self):
        if not self.concession_usage:
            return Decimal(0.00)
        concession = self.concession_usage.concesssion
        total_price = self.get_price_before_discounts()
        return Decimal(total_price * (concession.concession_percentage / 100))

    def get_discount_code_discount_as_amount(self):
        if not self.discount_code_usage:
            return Decimal(0.00)
        price_before_discounts = self.get_price_before_discounts()
        discount_code_batch = self.discount_code_usage.discount_code.discount_code_batch
        if discount_code_batch.discount_amount:
            return self.discount_code.discount_code_batch.discount_amount
        else:
            return price_before_discounts * (
                discount_code_batch.discount_percentage / 100
            )

    def get_voucher_discount_as_amount(self):
        if not self.voucher_transaction.voucher:
            return Decimal(0.00)
        if 0.00 >= self.voucher_transaction.voucher.amount:
            return Decimal(0.00)
        price_before_discounts = self.get_price_before_discounts()
        concession_discount_amount = self.get_concession_discount_as_amount()
        discount_code_discount_amount = self.get_discount_code_discount_as_amount()
        remaining_price = (
            price_before_discounts
            - concession_discount_amount
            - discount_code_discount_amount
        )
        if self.voucher_transaction.voucher.amount >= remaining_price:
            return remaining_price
        else:
            return self.voucher_transaction.voucher.amount
