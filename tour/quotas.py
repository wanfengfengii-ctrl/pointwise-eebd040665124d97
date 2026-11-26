from dataclasses import dataclass

from core import BusinessError

VENUE_IDS = ('east', 'west')


@dataclass(frozen=True)
class VenueQuotas:
    east: int
    west: int

    def for_venue(self, venue_id):
        require_venue(venue_id)
        return self.east if venue_id == 'east' else self.west


def require_venue(venue_id):
    if venue_id not in VENUE_IDS:
        raise BusinessError('invalid_venue', '馆别须为东馆或西馆。')
    return venue_id


def validate_quota(value):
    if type(value) is not int or value < 0:
        raise BusinessError('invalid_quota', '放映分额须为非负整数。')
    return value


def validate_quotas(east, west):
    return VenueQuotas(validate_quota(east), validate_quota(west))
