"""Who is staff. Owners come from env vars only, so a database problem can never lock the owner out."""

from amora.config import Settings
from amora.core.profiles import ProfileService
from amora.db.models import Platform, Role

_RANK = {Role.USER: 0, Role.MOD: 1, Role.ADMIN: 2, Role.OWNER: 3}


class AdminService:
    def __init__(self, settings: Settings, profiles: ProfileService):
        self.s = settings
        self.profiles = profiles

    def is_owner(self, platform: str, platform_user_id: int) -> bool:
        owners = self.s.owner_tg_ids if platform == Platform.TELEGRAM else self.s.owner_dc_ids
        return int(platform_user_id) in owners

    async def role_of(self, platform: str, platform_user_id: int) -> Role:
        if self.is_owner(platform, platform_user_id):
            return Role.OWNER
        user = await self.profiles.find_by_platform(platform, platform_user_id)
        return Role(user.role) if user else Role.USER

    async def has_role(self, platform: str, platform_user_id: int, minimum: Role) -> bool:
        return _RANK[await self.role_of(platform, platform_user_id)] >= _RANK[minimum]
