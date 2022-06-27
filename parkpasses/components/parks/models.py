"""
    This module contains the models required to impliment parks
    which are relevant for [local park passes].

    A postcode can have mutiple local parks associated with it.
    A local park can have mulitple postcodes it is relevant to.
"""
from django.core.validators import MinLengthValidator
from django.db import models


class Postcode(models.Model):
    """A class to represent a postcode"""

    postcode = models.CharField(
        unique=True,
        null=False,
        blank=False,
        max_length=4,
        validators=[
            MinLengthValidator(4, "Australian postcodes must contain 4 digits")
        ],
    )

    class Meta:
        app_label = "parkpasses"

    def __str__(self):
        return str(self.postcode)

    @property
    def local_park(self):
        return self.lgas.first().park


class Park(models.Model):
    """A class to represent a park"""

    image = models.ImageField(null=True, blank=True)
    name = models.CharField(unique=True, max_length=100, null=False, blank=False)
    display_externally = models.BooleanField(null=False, blank=False)

    class Meta:
        app_label = "parkpasses"

    def __str__(self):
        return self.name


class ParkGroupManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("parks")


class ParkGroup(models.Model):
    """A class to represent a group of parks"""

    name = models.CharField(unique=True, max_length=100, null=False, blank=False)
    parks = models.ManyToManyField(
        Park, related_name="park_groups", through="Member", blank=True
    )
    display_order = models.SmallIntegerField(unique=True, null=False, blank=False)
    display_externally = models.BooleanField(null=False, blank=False)

    class Meta:
        app_label = "parkpasses"
        verbose_name = "Park Group"
        verbose_name_plural = "Park Groups"

    def __str__(self):
        return self.name

    @classmethod
    def get_park_group_by_postcode(self, postcode):
        lga = LGA.objects.filter(postcodes__in=postcode).first()
        return lga.park_group


class MemberManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("park_group", "park")


class Member(models.Model):
    park_group = models.ForeignKey(ParkGroup, on_delete=models.CASCADE)
    park = models.ForeignKey(Park, on_delete=models.CASCADE)
    display_order = models.SmallIntegerField(null=False, blank=False)

    class Meta:
        app_label = "parkpasses"
        verbose_name = "Parks ParkGroups"
        verbose_name_plural = "Parks ParkGroups"
        unique_together = (("park_group", "display_order"),)


class LGAManager(models.Manager):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("park_group")
            .prefetch_related("postcodes")
        )


class LGA(models.Model):
    """A class to represent a local goverment area (LGA)"""

    objects = LGAManager()

    park_group = models.ForeignKey(
        ParkGroup, on_delete=models.PROTECT, null=True, blank=True
    )
    name = models.CharField(unique=True, max_length=50, null=False, blank=False)
    postcodes = models.ManyToManyField(Postcode, related_name="lgas", blank=True)

    class Meta:
        app_label = "parkpasses"
        verbose_name = "LGA"
        verbose_name_plural = "LGAs"

    def __str__(self):
        return self.name
