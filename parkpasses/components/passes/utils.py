"""
    This module provides utilities for the passes component
"""

import logging
import os
import subprocess
from pathlib import Path

import fitz
from django.conf import settings
from django.utils.dateformat import DateFormat
from docxtpl import DocxTemplate, RichText

logger = logging.getLogger(__name__)


class PassUtils:
    def generate_pass_pdf_from_docx_template(
        self, park_pass, pass_template_path, qr_code_path
    ):
        park_pass_docx = DocxTemplate(
            f"{settings.PROTECTED_MEDIA_ROOT}{pass_template_path}"
        )

        date_format = DateFormat(park_pass.date_start)
        date_start = date_format.format("jS F Y")

        date_format = DateFormat(park_pass.date_expiry)
        date_expiry = date_format.format("jS F Y")

        date_format = DateFormat(park_pass.datetime_created)
        datetime_created = date_format.format("jS F Y")

        pass_type = park_pass.option.pricing_window.pass_type
        pass_type_display_name = pass_type.display_name

        template_image = settings.PASS_TEMPLATE_DEFAULT_IMAGE_PATH

        if pass_type.template_image:
            template_image = pass_type.template_image.path

        concession_card_type = None
        concession_card_number = None

        display_name_colour = pass_type.display_name_colour

        if hasattr(park_pass, "concession_usage"):
            concession_usage = park_pass.concession_usage
            concession_card_number = concession_usage.concession_card_number
            concession_card_type = concession_usage.concession.concession_type
            display_name_colour = pass_type.concession_display_name_colour
            if pass_type.concession_template_image:
                template_image = pass_type.concession_template_image.path

        # This line replaces the background image in the docx file
        park_pass_docx.replace_zipname(
            settings.PASS_TEMPLATE_REPLACEMENT_IMAGE_PATH, template_image
        )

        park_group = None
        if park_pass.park_group:
            park_group = park_pass.park_group.name

        order_number = None
        order = park_pass.order
        if order:
            order_number = order.order_number

        rider_name = f"{park_pass.first_name} {park_pass.last_name}"

        rich_text_pass_type_display_name = RichText(
            pass_type_display_name,
            color=display_name_colour,
            size=28,
            bold=True,
        )

        if settings.USE_DUMMY_QR_CODE_DATA:
            # In a test environment, we don't add any personal data into the pass context
            context = {
                "pass_type": rich_text_pass_type_display_name,
                "pass_park_group": park_group,
                "pass_postcode": park_pass.postcode,
                "pass_number": park_pass.pass_number,
                "pass_concession_card_number": "CONC123123",
                "pass_concession_card_type": concession_card_type,
                "pass_start": date_start,
                "pass_expiry": date_expiry,
                "pass_vehicle_registration_1": "VehicleReg1",
                "pass_vehicle_registration_2": "VehicleReg2",
                "pass_drivers_licence_number": "L12312312",
                "pass_first_name": "John",
                "pass_last_name": "Smith",
                "pass_rider_name": "John Smith",
                "pass_purchase_date": datetime_created,
                "pass_order_number": order_number,
            }
        else:
            context = {
                "pass_type": rich_text_pass_type_display_name,
                "pass_park_group": park_group,
                "pass_postcode": park_pass.postcode,
                "pass_number": park_pass.pass_number,
                "pass_concession_card_number": concession_card_number,
                "pass_concession_card_type": concession_card_type,
                "pass_start": date_start,
                "pass_expiry": date_expiry,
                "pass_vehicle_registration_1": park_pass.vehicle_registration_1,
                "pass_vehicle_registration_2": park_pass.vehicle_registration_2,
                "pass_drivers_licence_number": park_pass.drivers_licence_number,
                "pass_first_name": park_pass.first_name,
                "pass_last_name": park_pass.last_name,
                "pass_rider_name": rider_name,
                "pass_purchase_date": datetime_created,
                "pass_order_number": order_number,
            }

        park_pass_docx.render(context)

        park_pass_file_path = f"{park_pass._meta.app_label}/"
        park_pass_file_path += (
            f"{park_pass._meta.model.__name__}/passes/{park_pass.user}/{park_pass.pk}/"
        )
        Path(settings.PROTECTED_MEDIA_ROOT + "/" + park_pass_file_path).mkdir(
            parents=True, exist_ok=True
        )

        park_pass_docx_file_name = "ParkPass.docx"
        park_pass_docx_full_file_path = (
            settings.PROTECTED_MEDIA_ROOT
            + "/"
            + park_pass_file_path
            + park_pass_docx_file_name
        )
        document_title = f"{pass_type_display_name} - {park_pass.first_name} {park_pass.last_name} - {datetime_created}"
        park_pass_docx.docx.core_properties.title = document_title
        park_pass_docx.save(f"{park_pass_docx_full_file_path}")
        output = subprocess.check_output(
            [
                "libreoffice",
                # "--headless",
                "--convert-to",
                "pdf",
                park_pass_docx_full_file_path,
                "--outdir",
                settings.PROTECTED_MEDIA_ROOT + "/" + park_pass_file_path,
            ]
        )

        logger.info(f"Subprocess output = {output}")

        park_pass_pdf_file_name = "ParkPass.pdf"
        park_pass_pdf_path = park_pass_file_path + park_pass_pdf_file_name
        new_path = park_pass_file_path + f"{park_pass.pass_number}.pdf"

        os.rename(
            settings.PROTECTED_MEDIA_ROOT + "/" + park_pass_pdf_path,
            settings.PROTECTED_MEDIA_ROOT + "/" + new_path,
        )

        park_pass.park_pass_pdf.name = new_path

        image_rectangle = fitz.Rect(409, 69, 529, 189)
        file_handle = fitz.open(park_pass.park_pass_pdf.path)
        first_page = file_handle[0]

        first_page.insert_image(image_rectangle, filename=qr_code_path)
        file_handle.saveIncr()

        # Clean up unused files
        # os.remove(park_pass_docx_full_file_path)

        logger.info(qr_code_path)
        # os.remove(qr_code_path)
