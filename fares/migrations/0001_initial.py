# Generated by Django 3.1.6 on 2021-02-04 16:28

import django.contrib.postgres.fields.ranges
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('busstops', '0006_auto_20201225_0004'),
    ]

    operations = [
        migrations.CreateModel(
            name='DataSet',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('url', models.URLField(blank=True)),
                ('description', models.CharField(max_length=255)),
                ('datetime', models.DateTimeField(blank=True, null=True)),
                ('operators', models.ManyToManyField(blank=True, to='busstops.Operator')),
            ],
        ),
        migrations.CreateModel(
            name='FareTable',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=255)),
                ('name', models.CharField(max_length=255)),
                ('description', models.CharField(blank=True, max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='PriceGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(blank=True, max_length=255)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=5)),
            ],
        ),
        migrations.CreateModel(
            name='SalesOfferPackage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(blank=True, max_length=255)),
                ('name', models.CharField(blank=True, max_length=255)),
                ('description', models.CharField(blank=True, max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='TimeInterval',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(blank=True, max_length=255)),
                ('name', models.CharField(max_length=255)),
                ('description', models.CharField(max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=255)),
                ('name', models.CharField(max_length=255)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('proof_required', models.CharField(blank=True, max_length=255)),
                ('discount_basis', models.CharField(blank=True, max_length=255)),
                ('min_age', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('max_age', models.PositiveSmallIntegerField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='TimeIntervalPrice',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(blank=True, max_length=255)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=5)),
                ('time_interval', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='fares.timeinterval')),
            ],
        ),
        migrations.CreateModel(
            name='Tariff',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=255)),
                ('name', models.CharField(max_length=255)),
                ('filename', models.CharField(max_length=255)),
                ('trip_type', models.CharField(max_length=255)),
                ('valid_between', django.contrib.postgres.fields.ranges.DateTimeRangeField(blank=True, null=True)),
                ('operators', models.ManyToManyField(blank=True, to='busstops.Operator')),
                ('services', models.ManyToManyField(blank=True, to='busstops.Service')),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='fares.dataset')),
                ('user_profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='fares.userprofile')),
            ],
        ),
        migrations.CreateModel(
            name='Row',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(blank=True, max_length=255)),
                ('name', models.CharField(max_length=255)),
                ('order', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('table', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='fares.faretable')),
            ],
        ),
        migrations.CreateModel(
            name='FareZone',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=255)),
                ('name', models.CharField(max_length=255)),
                ('stops', models.ManyToManyField(blank=True, to='busstops.StopPoint')),
            ],
        ),
        migrations.AddField(
            model_name='faretable',
            name='sales_offer_package',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='fares.salesofferpackage'),
        ),
        migrations.AddField(
            model_name='faretable',
            name='tariff',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='fares.tariff'),
        ),
        migrations.AddField(
            model_name='faretable',
            name='user_profile',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='fares.userprofile'),
        ),
        migrations.CreateModel(
            name='DistanceMatrixElement',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=255)),
                ('end_zone', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ending', to='fares.farezone')),
                ('price_group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='fares.pricegroup')),
                ('start_zone', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='starting', to='fares.farezone')),
                ('tariff', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='fares.tariff')),
            ],
        ),
        migrations.CreateModel(
            name='Column',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(blank=True, max_length=255)),
                ('name', models.CharField(max_length=255)),
                ('order', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('table', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='fares.faretable')),
            ],
        ),
        migrations.CreateModel(
            name='Cell',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('column', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='fares.column')),
                ('distance_matrix_element', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='fares.distancematrixelement')),
                ('price_group', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='fares.pricegroup')),
                ('row', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='fares.row')),
                ('time_interval_price', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='fares.timeintervalprice')),
            ],
        ),
    ]
