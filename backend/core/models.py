from django.db import models


class HubConfig(models.Model):
    """
    Settings for the single hub this app manages.
    There is only ever ONE row in this table (a "singleton").
    """

    REASONS_FORMAT_GROUPED = 'grouped'
    REASONS_FORMAT_TEXT = 'text'
    REASONS_FORMAT_CHOICES = [
        (REASONS_FORMAT_GROUPED, 'Grouped counts (e.g. Customer unavailable - 6)'),
        (REASONS_FORMAT_TEXT, 'Free text written by me'),
    ]

    hub_name = models.CharField(max_length=100)
    reasons_format = models.CharField(
        max_length=20,
        choices=REASONS_FORMAT_CHOICES,
        default=REASONS_FORMAT_GROUPED,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Hub configuration'
        verbose_name_plural = 'Hub configuration'

    def save(self, *args, **kwargs):
        # Force every save onto row id=1, so a second row can never exist.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        """Return the single config row, creating it if it doesn't exist yet."""
        config, _ = cls.objects.get_or_create(pk=1, defaults={'hub_name': 'My Hub'})
        return config

    def __str__(self):
        return self.hub_name


class StatusOption(models.Model):
    """
    A shipment status you can pick from the dropdown.
    The report maths uses `category`, never the name.
    """

    CATEGORY_UNCHECKED = 'unchecked'
    CATEGORY_OUTSTANDING = 'outstanding'
    CATEGORY_DELIVERED = 'delivered'
    CATEGORY_RETURNED = 'returned'
    CATEGORY_LEFT_HUB = 'left_hub'
    CATEGORY_CHOICES = [
        (CATEGORY_UNCHECKED, 'Not yet checked'),
        (CATEGORY_OUTSTANDING, 'Outstanding (still at hub, needs delivery)'),
        (CATEGORY_DELIVERED, 'Delivered'),
        (CATEGORY_RETURNED, 'Returned to hub'),
        (CATEGORY_LEFT_HUB, 'Left the hub (e.g. rerouted)'),
    ]

    name = models.CharField(max_length=60, unique=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    # If True, picking this status forces you to choose a FailureReason.
    requires_reason = models.BooleanField(default=False)
    # Controls the order in the dropdown (lower number = higher in list).
    sort_order = models.PositiveIntegerField(default=0)
    # Instead of deleting a status (which would damage history), switch it off.
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class FailureReason(models.Model):
    """
    A reason for an unsuccessful delivery.
    If `is_other` is True, a written explanation is required.
    """

    name = models.CharField(max_length=100, unique=True)
    is_other = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name