# Generated by Django 3.2.9 on 2021-12-22 16:37

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import standingsrequests.models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("authentication", "0019_merge_20211026_0919"),
        ("eveuniverse", "0005_type_materials_and_sections"),
        ("standingsrequests", "0009_make_ceo_optional"),
    ]

    operations = [
        migrations.CreateModel(
            name="FrozenAlt",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        choices=[("CH", "character"), ("CP", "corporation")],
                        max_length=2,
                    ),
                ),
                (
                    "alliance",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="eveuniverse.eveentity",
                    ),
                ),
                (
                    "character",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="eveuniverse.eveentity",
                    ),
                ),
                (
                    "corporation",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="eveuniverse.eveentity",
                    ),
                ),
                (
                    "faction",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="eveuniverse.eveentity",
                    ),
                ),
            ],
            bases=(standingsrequests.models.FrozenModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name="FrozenAuthUser",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "alliance",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="eveuniverse.eveentity",
                    ),
                ),
                (
                    "character",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="eveuniverse.eveentity",
                    ),
                ),
                (
                    "corporation",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="eveuniverse.eveentity",
                    ),
                ),
                (
                    "faction",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="eveuniverse.eveentity",
                    ),
                ),
                (
                    "state",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="authentication.state",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.SET(
                            standingsrequests.models.get_or_create_sentinel_user
                        ),
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            bases=(standingsrequests.models.FrozenModelMixin, models.Model),
        ),
        migrations.AddField(
            model_name="standingrequest",
            name="reason",
            field=models.CharField(
                choices=[
                    ("NO", "None recorded"),
                    ("OR", "Requested by character owner"),
                    ("LP", "Character owner has lost permission"),
                    ("CT", "Not all corp tokens are recorded in Auth."),
                    ("RG", "Standing has been revoked in game"),
                    ("SG", "Already has standing in game"),
                ],
                default="NO",
                max_length=2,
            ),
        ),
        migrations.AlterField(
            model_name="standingrevocation",
            name="reason",
            field=models.CharField(
                choices=[
                    ("NO", "None recorded"),
                    ("OR", "Requested by character owner"),
                    ("LP", "Character owner has lost permission"),
                    ("CT", "Not all corp tokens are recorded in Auth."),
                    ("RG", "Standing has been revoked in game"),
                    ("SG", "Already has standing in game"),
                ],
                default="NO",
                max_length=2,
            ),
        ),
        migrations.CreateModel(
            name="RequestLogEntry",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "action",
                    models.CharField(
                        choices=[("CN", "confirmed"), ("RJ", "rejected")], max_length=2
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now=True)),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("NO", "None recorded"),
                            ("OR", "Requested by character owner"),
                            ("LP", "Character owner has lost permission"),
                            ("CT", "Not all corp tokens are recorded in Auth."),
                            ("RG", "Standing has been revoked in game"),
                            ("SG", "Already has standing in game"),
                        ],
                        max_length=2,
                    ),
                ),
                (
                    "request_type",
                    models.CharField(
                        choices=[("RQ", "request"), ("RV", "revocation")], max_length=2
                    ),
                ),
                ("requested_at", models.DateTimeField()),
                (
                    "action_by",
                    models.ForeignKey(
                        help_text="Main who performed the action. None means the action was performed automatically by the app.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="standingsrequests.frozenauthuser",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="standingsrequests.frozenauthuser",
                    ),
                ),
                (
                    "requested_for",
                    models.ForeignKey(
                        help_text="Alt character or corporation to change standing for",
                        on_delete=django.db.models.deletion.CASCADE,
                        to="standingsrequests.frozenalt",
                    ),
                ),
            ],
            options={
                "verbose_name": "request log",
                "verbose_name_plural": "request log",
            },
            bases=(standingsrequests.models.FrozenModelMixin, models.Model),
        ),
    ]
