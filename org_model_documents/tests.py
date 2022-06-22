import tempfile

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings

from org_model_documents.models import Document


class DocumentTestCase(TestCase):
    @override_settings(MEDIA_ROOT=tempfile.TemporaryDirectory(prefix="mediatest").name)
    def setUp(self):
        file_field = tempfile.NamedTemporaryFile()
        file_field.name = "/tmp/imagine_being_the_best_file_eva.txt"
        file_field.write(b"Some things are supposed to remain as dreams!")
        self.content_type = ContentType.objects.get(
            app_label="parkpasses", model="park"
        )
        document = Document.objects.create(
            object_id=1, content_type=self.content_type, _file=file_field
        )
        self.object_id = document.object_id

    @override_settings(MEDIA_ROOT=tempfile.TemporaryDirectory(prefix="mediatest").name)
    def test_str(self):
        document = Document.objects.get(
            object_id=self.object_id, content_type=self.content_type
        )
        self.assertEqual(
            document.__str__(),
            "id 1 | content_type parkpasses | park | document \
                /media/org_model_documents/parkpasses%20%7C%20park/1/imagine_being_the_best_file_eva.txt",
        )

    @override_settings(MEDIA_ROOT=tempfile.TemporaryDirectory(prefix="mediatest").name)
    def test_path(self):
        document = Document.objects.get(
            object_id=self.object_id, content_type=self.content_type
        )
        self.assertEqual(
            document.path,
            settings.MEDIA_ROOT
            + "/org_model_documents/parkpasses | park/1/imagine_being_the_best_file_eva.txt",
        )
        document.path = None
        self.assertEqual(document.path, "")
