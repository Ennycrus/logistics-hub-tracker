from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_hubconfig_return_email_subject_and_more"),
        ("shipments", "0006_shipment_return_emailed_at_shipment_return_waybill"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="statushistory",
            index=models.Index(
                fields=["shipment", "effective_date"],
                name="shipments_s_shipmen_7ed967_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="statushistory",
            index=models.Index(
                fields=["shipment", "new_status"], name="shipments_s_shipmen_dcefa7_idx"
            ),
        ),
    ]