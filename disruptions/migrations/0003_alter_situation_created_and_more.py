# Generated by Django 5.0.6 on 2024-05-22 19:14

import disruptions.models
import django.contrib.postgres.fields.ranges
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('busstops', '0003_alter_stopcode_source'),
        ('disruptions', '0001_squashed_0002_rename_situation_current_publication_window_disruptions_current_cfec06_idx_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='situation',
            name='created',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='situation',
            name='publication_window',
            field=django.contrib.postgres.fields.ranges.DateTimeRangeField(default=disruptions.models.from_now),
        ),
        migrations.AlterField(
            model_name='situation',
            name='source',
            field=models.ForeignKey(default=236, limit_choices_to={'name__in': ('bustimes.org', 'TfL', 'Bus Open Data')}, on_delete=django.db.models.deletion.CASCADE, to='busstops.datasource'),
        ),
    ]
