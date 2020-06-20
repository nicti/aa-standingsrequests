from django.core.management.base import BaseCommand
from allianceauth.eveonline.models import EveCharacter

from ...models import ContactSet, PilotStanding, StandingsRequest, StandingsRevocation


def get_input(text):
    """wrapped input to enable unit testing / patching"""
    return input(text)


class Command(BaseCommand):
    help = "Create standing request for alts with standing in game"

    def _create_requests(self):
        contact_set = ContactSet.objects.latest()
        owned_characters_qs = EveCharacter.objects.filter(
            character_ownership__isnull=False
        ).select_related()
        created_counter = 0
        for alt in owned_characters_qs:
            user = alt.character_ownership.user
            if (
                StandingsRequest.has_required_scopes_for_request(alt)
                and not StandingsRequest.objects.filter(
                    user=user, contact_id=alt.character_id
                ).exists()
                and not StandingsRevocation.objects.filter(
                    contact_id=alt.character_id
                ).exists()
            ):
                if not ContactSet.pilot_in_organisation(
                    alt.character_id
                ) and contact_set.has_pilot_standing(alt.character_id):
                    sr = StandingsRequest.objects.add_request(
                        user,
                        alt.character_id,
                        PilotStanding.get_contact_type_id(alt.character_id),
                    )
                    sr.mark_standing_actioned(None)
                    sr.mark_standing_effective()
                    self.stdout.write(
                        f"Created standings request for blue character '{alt}' "
                        f"belonging to user '{user}'."
                    )
                    created_counter += 1

        self.stdout.write(f"Created a total of {created_counter} standing requests.")

    def handle(self, *args, **options):
        self.stdout.write(
            "This command will automatically create accepted standings requests for "
            "alt characters on Auth that already have blue standing in-game."
        )
        user_input = get_input("Are you sure you want to proceed? (Y/n)?")
        if user_input == "Y":
            self.stdout.write("Starting update. Please stand by.")
            self._create_requests()
            self.stdout.write(self.style.SUCCESS("Process completed!"))
        else:
            self.stdout.write(self.style.WARNING("Aborted"))
