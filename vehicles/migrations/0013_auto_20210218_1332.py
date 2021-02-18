# Generated by Django 3.1.6 on 2021-02-18 13:32

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('bustimes', '0006_auto_20210115_1956'),
        ('vehicles', '0012_auto_20210210_1456'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehicle',
            name='garage',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='bustimes.garage'),
        ),
        migrations.AddField(
            model_name='vehicle',
            name='latest_journey',
            field=models.OneToOneField(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='latest_vehicle', to='vehicles.vehiclejourney'),
        ),
    ]
