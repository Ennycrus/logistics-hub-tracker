from django.db import migrations

# (name, category, requires_reason, sort_order)
DEFAULT_STATUSES = [
    ('Not Yet Checked', 'unchecked', False, 1),
    ('Pending Delivery', 'outstanding', False, 2),
    ('Delivered Successfully', 'delivered', False, 3),
    ('Delivery Unsuccessful', 'outstanding', True, 4),
    ('Returned to Hub', 'returned', False, 5),
    ('Rerouted to Another Hub', 'left_hub', False, 6),
]

# (name, is_other, sort_order)
DEFAULT_REASONS = [
    ('Customer unavailable', False, 1),
    ('Customer requested rescheduling', False, 2),
    ('Incorrect or incomplete address', False, 3),
    ('Unable to contact customer', False, 4),
    ('Customer refused delivery', False, 5),
    ('Other', True, 6),
]


def seed_defaults(apps, schema_editor):
    # Use apps.get_model, NOT a normal import. A migration must use the model
    # as it was at THIS point in history, not whatever models.py says later.
    StatusOption = apps.get_model('core', 'StatusOption')
    FailureReason = apps.get_model('core', 'FailureReason')

    for name, category, requires_reason, order in DEFAULT_STATUSES:
        # get_or_create: skip any row that already exists (e.g. the one
        # you added by hand), so we never hit the unique-name error.
        StatusOption.objects.get_or_create(
            name=name,
            defaults={
                'category': category,
                'requires_reason': requires_reason,
                'sort_order': order,
            },
        )

    for name, is_other, order in DEFAULT_REASONS:
        FailureReason.objects.get_or_create(
            name=name,
            defaults={'is_other': is_other, 'sort_order': order},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        # noop = do nothing when this migration is reversed.
        # We don't want to delete statuses that shipments may already use.
        migrations.RunPython(seed_defaults, migrations.RunPython.noop),
    ]