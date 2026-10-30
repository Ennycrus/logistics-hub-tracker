"""
Give every existing shipment the right type, from its waybill prefix:
    starts with 3034 -> TEMU
    starts with 1    -> Base
Anything else stays TEMU (the old default), so nothing is lost.
"""

from django.db import migrations


def fill_types(apps, schema_editor):
    Shipment = apps.get_model('shipments', 'Shipment')
    Shipment.objects.filter(waybill_number__startswith='3034').update(shipment_type='temu')
    Shipment.objects.filter(waybill_number__startswith='1').update(shipment_type='base')
    Shipment.objects.exclude(shipment_type__in=['base', 'temu']).update(shipment_type='temu')


class Migration(migrations.Migration):

    dependencies = [
        ('shipments', '0003_shipment_types'),
    ]

    operations = [
        migrations.RunPython(fill_types, migrations.RunPython.noop),
    ]