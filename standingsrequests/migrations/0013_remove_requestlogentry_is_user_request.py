# Generated by Django 3.2.9 on 2021-12-19 18:59

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("standingsrequests", "0012_alter_requestlogentry_options"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="requestlogentry",
            name="is_user_request",
        ),
    ]
