# Generated by Django 3.2.16 on 2023-02-01 01:20

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('parkpasses', '0153_passtype_concession_display_name_colour'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='report',
            name='invoice',
        ),
    ]
