import logging

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework_datatables.filters import DatatablesFilterBackend
from rest_framework_datatables.pagination import DatatablesPageNumberPagination

from parkpasses.components.discount_codes.models import (
    DiscountCode,
    DiscountCodeBatch,
    DiscountCodeBatchComment,
)
from parkpasses.components.discount_codes.serializers import (
    InternalDiscountCodeBatchCommentSerializer,
    InternalDiscountCodeBatchSerializer,
    InternalDiscountCodeSerializer,
)

logger = logging.getLogger(__name__)


class DiscountCodeViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for performing actions on discount codes.
    """

    model = DiscountCode
    queryset = DiscountCode.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = InternalDiscountCodeSerializer


class DiscountCodeBatchViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for performing actions on discount code batches.
    """

    model = DiscountCodeBatch
    pagination_class = DatatablesPageNumberPagination
    queryset = DiscountCodeBatch.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = InternalDiscountCodeBatchSerializer
    filter_backends = (DatatablesFilterBackend,)
    filterset_fields = [
        "times_each_code_can_be_used",
    ]


class DiscountCodeBatchCommentViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for performing actions on discount code batches.
    """

    model = DiscountCodeBatchComment
    queryset = DiscountCodeBatchComment.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = InternalDiscountCodeBatchCommentSerializer
