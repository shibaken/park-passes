import logging

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.management import call_command
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic.base import TemplateView

from parkpasses.forms import LoginForm
from parkpasses.helpers import is_internal, is_retailer, is_retailer_admin

logger = logging.getLogger(__name__)


class InternalView(UserPassesTestMixin, TemplateView):
    template_name = "parkpasses/internal/index.html"

    def test_func(self):
        return is_internal(self.request)


class RetailerView(UserPassesTestMixin, TemplateView):
    template_name = "parkpasses/retailer/index.html"

    def test_func(self):
        return is_retailer(self.request)


class RetailerSellAPassView(UserPassesTestMixin, TemplateView):
    template_name = "parkpasses/retailer/index.html"

    def test_func(self):
        return is_retailer(self.request)

    def get(self, *args, **kwargs):
        cart_item_count = self.request.session.get("cart_item_count", None)

        if cart_item_count and cart_item_count > 0:
            return redirect(reverse("user-cart"))

        return super().get(*args, **kwargs)


class RetailerAdminView(UserPassesTestMixin, TemplateView):
    template_name = "parkpasses/retailer/index.html"

    def test_func(self):
        return is_retailer_admin(self.request)


class ExternalView(LoginRequiredMixin, TemplateView):
    template_name = "parkpasses/dash/index.html"


class ParkPassesRoutingView(TemplateView):
    template_name = "parkpasses/index.html"

    def get(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            if is_internal(self.request):
                return redirect("internal")
            if is_retailer(self.request):
                return redirect("retailer-home")
        kwargs["form"] = LoginForm
        return super().get(*args, **kwargs)


class ParkPassesPurchaseVoucherView(TemplateView):
    template_name = "parkpasses/index.html"


class ParkPassesPurchasePassView(TemplateView):
    template_name = "parkpasses/index.html"


class ParkPassesContactView(TemplateView):
    template_name = "parkpasses/contact.html"


class ParkPassesFurtherInformationView(TemplateView):
    template_name = "parkpasses/further_info.html"


class ManagementCommandsView(LoginRequiredMixin, TemplateView):
    template_name = "parkpasses/mgt-commands.html"

    def post(self, request):
        data = {}
        command_script = request.POST.get("script", None)
        if command_script:
            print(f"running {command_script}")
            call_command(command_script)
            data.update({command_script: "true"})

        return render(request, self.template_name, data)
