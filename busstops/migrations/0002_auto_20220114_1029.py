# Generated by Django 3.2.11 on 2022-01-14 10:29

import django.contrib.gis.db.models.fields
import django.contrib.postgres.search
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('busstops', '0001_squashed_0010_auto_20210930_1810'),
    ]

    operations = [
        migrations.AddField(
            model_name='adminarea',
            name='created_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='adminarea',
            name='modified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='district',
            name='created_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='district',
            name='modified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='locality',
            name='created_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='locality',
            name='modified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='locality',
            name='short_name',
            field=models.CharField(blank=True, max_length=48),
        ),
        migrations.AddField(
            model_name='stoppoint',
            name='created_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='stoppoint',
            name='modified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='stoppoint',
            name='revision_number',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='stoppoint',
            name='search_vector',
            field=django.contrib.postgres.search.SearchVectorField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='stoppoint',
            name='short_common_name',
            field=models.CharField(blank=True, max_length=48),
        ),
        migrations.AlterField(
            model_name='service',
            name='geometry',
            field=django.contrib.gis.db.models.fields.GeometryField(editable=False, null=True, srid=4326),
        ),
        migrations.AlterField(
            model_name='stoppoint',
            name='latlong',
            field=django.contrib.gis.db.models.fields.PointField(blank=True, null=True, srid=4326),
        ),
    ]