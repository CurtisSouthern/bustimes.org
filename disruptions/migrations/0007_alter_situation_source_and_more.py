# Generated by Django 4.1.4 on 2022-12-09 17:01

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("busstops", "0011_operatorgroup_operator_group"),
        ("disruptions", "0006_alter_situation_source"),
    ]

    operations = [
        migrations.AlterField(
            model_name="situation",
            name="source",
            field=models.ForeignKey(
                limit_choices_to={
                    "name__in": (
                        "Ito World",
                        "TfE",
                        "TfL",
                        "Transport for the North",
                        "Transport for West Midlands",
                        "bustimes.org",
                    )
                },
                on_delete=django.db.models.deletion.CASCADE,
                to="busstops.datasource",
            ),
        ),
        migrations.AlterIndexTogether(
            name="situation",
            index_together={("current", "publication_window")},
        ),
    ]