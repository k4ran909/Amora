"""Discord adapter. Phase 0: online with /dating and /admin. Full profile flow arrives in phase 3."""

import logging

import discord
from discord import app_commands

from amora.config import Settings
from amora.core.admin import AdminService
from amora.core.profiles import ProfileService
from amora.db.models import Platform, Role

log = logging.getLogger(__name__)

BRAND_COLOR = discord.Color.from_rgb(255, 122, 69)  # flame orange from assets/logo.png
LOGO_URL = "https://raw.githubusercontent.com/k4ran909/Amora/master/assets/avatar-512.png"


class AmoraDiscord(discord.Client):
    def __init__(self, settings: Settings, profiles: ProfileService, admin: AdminService):
        super().__init__(intents=discord.Intents.default())
        self.settings = settings
        self.profiles = profiles
        self.admin = admin
        self.tree = app_commands.CommandTree(self)
        self._register_commands()

    async def setup_hook(self) -> None:
        if self.settings.discord_guild_id:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Discord commands synced to guild %s", self.settings.discord_guild_id)
        else:
            await self.tree.sync()
            log.info("Discord commands synced globally (can take up to an hour to appear)")

    async def on_ready(self) -> None:
        log.info("Discord bot %s online in %d server(s)", self.user, len(self.guilds))

    def _register_commands(self) -> None:
        app = self.settings.app_name

        @self.tree.command(name="dating", description=f"Open {app}, the dating bot")
        async def dating(interaction: discord.Interaction) -> None:
            await self.profiles.get_or_create(Platform.DISCORD, interaction.user.id, interaction.user.name)
            embed = discord.Embed(
                title=f"💘 {app}",
                description=(
                    "Meet real people, with no catfish. Every photo is face-checked and every profile is "
                    "reviewed by our team.\n\n"
                    "🚧 **Profiles on Discord are coming very soon.** "
                    "Meanwhile you can create your profile on our Telegram bot. "
                    "Later you'll be able to link both accounts."
                ),
                color=BRAND_COLOR,
            )
            embed.set_thumbnail(url=LOGO_URL)
            embed.set_footer(text="18+ only · be respectful · report anything suspicious")
            await interaction.response.send_message(embed=embed, ephemeral=True)

        @self.tree.command(name="admin", description="Staff panel")
        async def admin_cmd(interaction: discord.Interaction) -> None:
            role = await self.admin.role_of(Platform.DISCORD, interaction.user.id)
            if role == Role.USER:
                await interaction.response.send_message("⛔ Staff only.", ephemeral=True)
                return
            by_status = await self.profiles.count_by_status()
            by_platform = await self.profiles.count_by_platform()
            embed = discord.Embed(title="🛠 Admin panel", color=BRAND_COLOR)
            embed.add_field(name="Your role", value=role.value.title(), inline=False)
            embed.add_field(name="Accounts", value="\n".join(f"{k}: {v}" for k, v in sorted(by_status.items())) or "none")
            embed.add_field(name="Platforms", value="\n".join(f"{k}: {v}" for k, v in sorted(by_platform.items())) or "none")
            embed.set_footer(text="Review queue buttons on Discord arrive in phase 3. Use /admin on Telegram for now.")
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def run_discord(settings: Settings, profiles: ProfileService, admin: AdminService) -> None:
    client = AmoraDiscord(settings, profiles, admin)
    async with client:
        await client.start(settings.discord_bot_token)
