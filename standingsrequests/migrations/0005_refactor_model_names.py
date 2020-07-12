# Generated by Django 2.2.13 on 2020-07-07 19:43

from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("standingsrequests", "0004_fix_types_and_indices"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="AllianceStanding", new_name="AllianceContact",
        ),
        migrations.RenameModel(old_name="PilotStanding", new_name="CharacterContact",),
        migrations.RenameModel(old_name="CorpStanding", new_name="CorporationContact",),
        migrations.RenameModel(old_name="EveNameCache", new_name="EveEntity",),
        migrations.RenameModel(
            old_name="StandingsRequest", new_name="StandingRequest",
        ),
        migrations.RenameModel(
            old_name="StandingsRevocation", new_name="StandingRevocation",
        ),
    ]