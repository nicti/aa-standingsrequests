# Generated by Django 3.2.9 on 2021-12-19 17:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("standingsrequests", "0009_make_ceo_optional"),
    ]

    operations = [
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
                        choices=[("AP", "approved"), ("RJ", "rejected")], max_length=2
                    ),
                ),
                ("action_by", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now=True)),
                ("is_user_request", models.BooleanField()),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("NO", "None recorded"),
                            ("OR", "Requested by character owner"),
                            ("LP", "Character owner has lost permission"),
                            ("CT", "Not all corp tokens are recorded in Auth."),
                            ("RG", "Standing has been revoked in game"),
                        ],
                        default="NO",
                        max_length=2,
                    ),
                ),
                (
                    "request_type",
                    models.CharField(
                        choices=[("RQ", "request"), ("RV", "revocation")], max_length=2
                    ),
                ),
                ("requested_on", models.DateTimeField()),
                ("requested_by", models.CharField(default="", max_length=255)),
            ],
        ),
    ]
