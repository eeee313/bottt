"""
GAG 2 MM Services - Discord Bot
Full ticket system + moderation system + role/rank system.

Run with:  python bot.py
Requires:  DISCORD_TOKEN in your .env / Railway variables.
"""

import os
import json
import asyncio
import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# =========================================================
#  CONFIG  -  edit these to match your server if anything
#  ever changes. IDs below come from what you gave me.
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("PREFIX", "+")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))  # optional, speeds up slash sync

# ---- Channels ----
ROLE_LOG_CHANNEL_ID = 1528865980988788861          # transcript role log
MOD_LOG_CHANNEL_ID = 1528865970699898971           # moderation log
TRANSCRIPTS_CHANNEL_ID = 1528865962588373154       # ticket transcripts
TICKET_CATEGORY_ID = 1527856283498184876           # middleman ticket category
SUPPORT_TICKET_CATEGORY_ID = 1528491782491345107   # /supportpanel ticket category

# ---- Roles (lowest -> highest authority) ----
ROLE_GIVEAWAY_PING = 1528463410562601131
ROLE_TRIAL_MM = 1528463468737466469
ROLE_MM = 1528463607543894067
ROLE_LEAD_MM = 1528463688154218618
ROLE_MODERATOR = 1528463980329439325
ROLE_COORDINATOR = 1528465524424573149
ROLE_OVERSEER = 1528465730176290857
ROLE_HEAD_MANAGEMENT = 1528465890302230618
ROLE_HEAD_COORDINATION = 1528466122238591198
ROLE_HEAD_OPERATIONS = 1528466496890605660
ROLE_HEAD_DEV = 1528466008170303559
ROLE_HEAD_STAFF = 1528466750956376094
ROLE_PRESIDENT = 1528466975464882290

# Ordered lowest -> highest, used for hierarchy checks + /managerole
ROLE_HIERARCHY = [
    ROLE_TRIAL_MM,
    ROLE_MM,
    ROLE_LEAD_MM,
    ROLE_MODERATOR,
    ROLE_COORDINATOR,
    ROLE_OVERSEER,
    ROLE_HEAD_MANAGEMENT,
    ROLE_HEAD_COORDINATION,
    ROLE_HEAD_OPERATIONS,
    ROLE_HEAD_DEV,
    ROLE_HEAD_STAFF,
    ROLE_PRESIDENT,
]

ROLE_NAMES = {
    ROLE_GIVEAWAY_PING: "Giveaway Pings",
    ROLE_TRIAL_MM: "Trial Middleman",
    ROLE_MM: "Middleman",
    ROLE_LEAD_MM: "Lead Middleman",
    ROLE_MODERATOR: "Moderator",
    ROLE_COORDINATOR: "Coordinator",
    ROLE_OVERSEER: "Overseer",
    ROLE_HEAD_MANAGEMENT: "Head of Management",
    ROLE_HEAD_COORDINATION: "Head of Coordination",
    ROLE_HEAD_OPERATIONS: "Head of Operations",
    ROLE_HEAD_DEV: "Head of Dev",
    ROLE_HEAD_STAFF: "Head of Staff",
    ROLE_PRESIDENT: "President",
}

# Requirement text shown in +info
ROLE_REQUIREMENTS = [
    (ROLE_TRIAL_MM, "5 hits OR $5"),
    (ROLE_MM, "10 hits OR $10 | $5 if already Trial Middleman"),
    (ROLE_LEAD_MM, "20 hits OR $15 | $7 if already Middleman"),
    (ROLE_MODERATOR, "30 hits OR $25 | $10 if already Lead Middleman"),
    (ROLE_COORDINATOR, "50 hits OR $25 | $15 if already Moderator"),
    (ROLE_OVERSEER, "$50 | $35 if already Coordinator"),
    (ROLE_HEAD_MANAGEMENT, "$75 | $50 if already Overseer"),
    (ROLE_HEAD_COORDINATION, "$100 | $70 if already Head of Management"),
    (ROLE_HEAD_OPERATIONS, "$150 | $100 if already Head of Coordination"),
    (ROLE_HEAD_DEV, "$200 | $150 if already Head of Operations"),
    (ROLE_HEAD_STAFF, "$300 | $200 if already Head of Dev"),
    (ROLE_PRESIDENT, "$500 | $350 if already Head of Staff"),
]

# Perms text shown in +perks
ROLE_PERKS = [
    (ROLE_GIVEAWAY_PING, "Get this role after accepting the Mercy Program, hitters only."),
    (ROLE_TRIAL_MM, "Claim tickets, handle tickets, use middleman commands, view transcripts."),
    (ROLE_MM, "Claim tickets, handle tickets, use middleman commands, view transcripts, warn members."),
    (ROLE_LEAD_MM, "Claim tickets, handle tickets, use middleman commands, view transcripts, warn members."),
    (ROLE_MODERATOR, "Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members."),
    (ROLE_COORDINATOR, "Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members."),
    (ROLE_OVERSEER, "Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members, ban members, unban members, sell Trial Middleman, promote Trial Middleman."),
    (ROLE_HEAD_MANAGEMENT, "All Overseer perks, sell and promote Overseer and below."),
    (ROLE_HEAD_COORDINATION, "All Overseer perks, sell and promote Head of Management and below."),
    (ROLE_HEAD_OPERATIONS, "All Overseer perks, sell and promote Head of Coordination and below."),
    (ROLE_HEAD_DEV, "All Overseer perks, sell and promote Head of Operations and below."),
    (ROLE_HEAD_STAFF, "All Overseer perks, sell and promote Head of Development and below."),
    (ROLE_PRESIDENT, "Admin perms, can do everything below, and sell all roles below."),
]

EMBED_COLOR = 0x2B2D31
ACCENT_COLOR = 0x5865F2

# =========================================================
#  PERSISTENCE (simple JSON store - warnings/cooldowns/tickets)
# =========================================================

DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")


def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {"warnings": {}, "ban_cooldowns": {}, "ticket_count": 0, "tickets": {}}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


data_store = load_data()

# =========================================================
#  BOT SETUP
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)


# =========================================================
#  PERMISSION HELPERS
# =========================================================

def member_role_level(member: discord.Member) -> int:
    """Highest index in ROLE_HIERARCHY the member holds, -1 if none."""
    level = -1
    member_role_ids = {r.id for r in member.roles}
    for i, rid in enumerate(ROLE_HIERARCHY):
        if rid in member_role_ids:
            level = i
    return level


def has_min_role(member: discord.Member, min_role_id: int) -> bool:
    if member.guild_permissions.administrator:
        return True
    min_level = ROLE_HIERARCHY.index(min_role_id)
    return member_role_level(member) >= min_level


def can_claim_tickets(member: discord.Member) -> bool:
    return has_min_role(member, ROLE_TRIAL_MM)


def can_warn(member: discord.Member) -> bool:
    return has_min_role(member, ROLE_MM)


def can_moderate(member: discord.Member) -> bool:
    """mute / unmute / timeout"""
    return has_min_role(member, ROLE_MODERATOR)


def can_ban(member: discord.Member) -> bool:
    return has_min_role(member, ROLE_OVERSEER)


def can_manage_roles(member: discord.Member) -> bool:
    return has_min_role(member, ROLE_HEAD_MANAGEMENT)


async def log_to_channel(guild: discord.Guild, channel_id: int, embed: discord.Embed, file: Optional[discord.File] = None):
    channel = guild.get_channel(channel_id)
    if channel:
        try:
            if file:
                await channel.send(embed=embed, file=file)
            else:
                await channel.send(embed=embed)
        except discord.HTTPException:
            pass


# =========================================================
#  TICKET SYSTEM
# =========================================================

def build_ticket_embed(opener: discord.Member, answers: dict) -> discord.Embed:
    embed = discord.Embed(
        title="💎 Middleman Ticket Created",
        description="Your middleman ticket has been successfully created!\nA **middleman** will join shortly to assist with your trade.",
        color=ACCENT_COLOR,
    )
    embed.add_field(name="User", value=opener.mention, inline=True)
    embed.add_field(name="Status", value="🟢 Open", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)
    embed.add_field(name="Who is the other person?", value=answers["other_person"], inline=False)
    embed.add_field(name="What is the trade?", value=answers["trade"], inline=False)
    embed.add_field(name="Did both agree to this trade?", value=answers["agreed"], inline=False)
    embed.add_field(name="Can you join a private server?", value=answers["private_server"], inline=False)
    embed.set_footer(text="Thank you for keeping your trade safe, smooth, and secure! • GAG 2 MM Services")
    embed.timestamp = discord.utils.utcnow()
    return embed


class MMTicketModal(discord.ui.Modal, title="MM Ticket Request"):
    other_person = discord.ui.TextInput(
        label="Who is the other person?",
        placeholder="Enter their Discord username and ID",
        required=True,
        max_length=200,
    )
    trade = discord.ui.TextInput(
        label="What is the trade?",
        placeholder="Describe the items/game/currency being traded",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500,
    )
    agreed = discord.ui.TextInput(
        label="Did both agree to this trade?",
        placeholder="Yes/No with proof if possible",
        required=True,
        max_length=200,
    )
    private_server = discord.ui.TextInput(
        label="Can you join a private server?",
        placeholder="Yes/No (link will be provided)",
        required=True,
        max_length=200,
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        category = guild.get_channel(TICKET_CATEGORY_ID)
        if category is None:
            await interaction.response.send_message(
                "⚠️ Ticket category not found. Contact an admin.", ephemeral=True
            )
            return

        data_store["ticket_count"] += 1
        ticket_num = data_store["ticket_count"]
        channel_name = f"mm-{interaction.user.name}-{ticket_num}"[:100]

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            ),
        }
        for rid in (ROLE_TRIAL_MM, ROLE_MM, ROLE_LEAD_MM, ROLE_MODERATOR):
            role = guild.get_role(rid)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                )

        try:
            channel = await guild.create_text_channel(
                channel_name, category=category, overwrites=overwrites
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "⚠️ I couldn't create the ticket channel — Discord is requiring two-factor "
                "authentication on the account that owns this bot application. Enable 2FA on "
                "that Discord account (or ask an admin to), then try again.",
                ephemeral=True,
            )
            return

        answers = {
            "other_person": self.other_person.value,
            "trade": self.trade.value,
            "agreed": self.agreed.value,
            "private_server": self.private_server.value,
        }
        data_store["tickets"][str(channel.id)] = {
            "opener_id": interaction.user.id,
            "claimed_by": None,
            "status": "open",
            "type": "middleman",
        }
        save_data(data_store)

        embed = build_ticket_embed(interaction.user, answers)
        embed.description = (
            f"{interaction.user.mention}\n\n" + embed.description
        )
        await channel.send(
            content=f"{interaction.user.mention}", embed=embed, view=TicketControlView()
        )

        await interaction.response.send_message(
            f"✅ Your ticket has been created: {channel.mention}", ephemeral=True
        )

        log_embed = discord.Embed(
            title="🎫 Ticket Opened",
            description=f"**Channel:** {channel.mention}\n**Opened by:** {interaction.user.mention}",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        await log_to_channel(guild, MOD_LOG_CHANNEL_ID, log_embed)


class SupportTicketModal(discord.ui.Modal, title="Support Ticket"):
    reason = discord.ui.TextInput(
        label="What do you need help with?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        category = guild.get_channel(SUPPORT_TICKET_CATEGORY_ID)
        if category is None:
            await interaction.response.send_message(
                "⚠️ Support category not found. Contact an admin.", ephemeral=True
            )
            return

        data_store["ticket_count"] += 1
        ticket_num = data_store["ticket_count"]
        channel_name = f"support-{interaction.user.name}-{ticket_num}"[:100]

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            ),
        }
        for rid in (ROLE_TRIAL_MM, ROLE_MM, ROLE_LEAD_MM, ROLE_MODERATOR):
            role = guild.get_role(rid)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                )

        try:
            channel = await guild.create_text_channel(
                channel_name, category=category, overwrites=overwrites
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "⚠️ I couldn't create the ticket channel — Discord is requiring two-factor "
                "authentication on the account that owns this bot application. Enable 2FA on "
                "that Discord account (or ask an admin to), then try again.",
                ephemeral=True,
            )
            return

        data_store["tickets"][str(channel.id)] = {
            "opener_id": interaction.user.id,
            "claimed_by": None,
            "status": "open",
            "type": "support",
        }
        save_data(data_store)

        embed = discord.Embed(
            title="🛠️ Support Ticket Created",
            description=f"{interaction.user.mention}\n\n**Reason:**\n{self.reason.value}",
            color=ACCENT_COLOR,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="A staff member will be with you shortly • GAG 2 MM Services")

        await channel.send(
            content=f"{interaction.user.mention}", embed=embed, view=TicketControlView()
        )
        await interaction.response.send_message(
            f"✅ Your support ticket has been created: {channel.mention}", ephemeral=True
        )


class TicketRequestView(discord.ui.View):
    """Persistent view for the middleman request panel."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Request Middleman",
        emoji="💎",
        style=discord.ButtonStyle.blurple,
        custom_id="mm:request_middleman",
    )
    async def request_middleman(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MMTicketModal())


class SupportPanelView(discord.ui.View):
    """Persistent view for the /support panel."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Open Support Ticket",
        emoji="🎫",
        style=discord.ButtonStyle.blurple,
        custom_id="support:open_ticket",
    )
    async def open_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SupportTicketModal())


class TicketControlView(discord.ui.View):
    """Persistent view attached to every ticket channel (Claim / Unclaim / Close)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.green, custom_id="ticket:claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_claim_tickets(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("You don't have permission to claim tickets."), ephemeral=True
            )
            return
        info = data_store["tickets"].get(str(interaction.channel.id))
        if info is None:
            await interaction.response.send_message(
                embed=error_embed("This isn't a tracked ticket."), ephemeral=True
            )
            return
        if info.get("claimed_by"):
            claimer = interaction.guild.get_member(info["claimed_by"])
            await interaction.response.send_message(
                embed=error_embed(f"Already claimed by {claimer.mention if claimer else 'someone'}."),
                ephemeral=True,
            )
            return
        info["claimed_by"] = interaction.user.id
        save_data(data_store)
        embed = discord.Embed(
            title="✅ Ticket Claimed",
            description=f"This ticket is now being handled by {interaction.user.mention}.",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.gray, custom_id="ticket:unclaim")
    async def unclaim(self, interaction: discord.Interaction, button: discord.ui.Button):
        info = data_store["tickets"].get(str(interaction.channel.id))
        if info is None:
            await interaction.response.send_message(
                embed=error_embed("This isn't a tracked ticket."), ephemeral=True
            )
            return
        if info.get("claimed_by") != interaction.user.id and not can_manage_roles(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("Only the staff member who claimed this ticket can unclaim it."),
                ephemeral=True,
            )
            return
        info["claimed_by"] = None
        save_data(data_store)
        embed = discord.Embed(
            title="↩️ Ticket Unclaimed",
            description=f"{interaction.user.mention} has unclaimed this ticket. Another staff member can claim it now.",
            color=discord.Color.light_grey(),
            timestamp=discord.utils.utcnow(),
        )
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red, custom_id="ticket:close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        info = data_store["tickets"].get(str(interaction.channel.id))
        is_opener = info and info.get("opener_id") == interaction.user.id
        if not (can_claim_tickets(interaction.user) or is_opener):
            await interaction.response.send_message(
                embed=error_embed("You don't have permission to close this ticket."), ephemeral=True
            )
            return
        embed = discord.Embed(
            title="🔒 Closing Ticket",
            description="This ticket will close in 5 seconds...",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed)
        await close_ticket_channel(interaction.channel, interaction.user)


def error_embed(message: str) -> discord.Embed:
    return discord.Embed(description=f"❌ {message}", color=discord.Color.red())


async def close_ticket_channel(channel: discord.TextChannel, closer: discord.Member):
    """Builds a full text transcript, posts it to the transcripts channel, then deletes the ticket."""
    lines = []
    async for msg in channel.history(limit=None, oldest_first=True):
        ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        content = msg.content or "[embed/attachment]"
        lines.append(f"[{ts}] {msg.author}: {content}")

    transcript_text = "\n".join(lines) if lines else "No messages."
    file_path = f"/tmp/transcript-{channel.id}.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(transcript_text)

    info = data_store["tickets"].get(str(channel.id), {})
    opener = channel.guild.get_member(info.get("opener_id")) if info.get("opener_id") else None
    claimer = channel.guild.get_member(info.get("claimed_by")) if info.get("claimed_by") else None

    embed = discord.Embed(
        title=f"📁 Transcript - {channel.name}",
        color=discord.Color.dark_grey(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Opened by", value=opener.mention if opener else "Unknown", inline=True)
    embed.add_field(name="Claimed by", value=claimer.mention if claimer else "Nobody", inline=True)
    embed.add_field(name="Closed by", value=closer.mention, inline=True)
    await log_to_channel(
        channel.guild, TRANSCRIPTS_CHANNEL_ID, embed, file=discord.File(file_path)
    )

    if str(channel.id) in data_store["tickets"]:
        data_store["tickets"][str(channel.id)]["status"] = "closed"
        save_data(data_store)

    await asyncio.sleep(5)
    try:
        await channel.delete()
    except discord.HTTPException:
        pass
    os.remove(file_path)



# =========================================================
#  SLASH COMMANDS - TICKET MANAGEMENT
# =========================================================

@bot.tree.command(name="middleman", description="Post the middleman request panel in this channel.")
@app_commands.checks.has_permissions(manage_guild=True)
async def middleman_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="GAG 2 MM Services | MM Service",
        description=(
            "Welcome to our middleman Service centre.\n\n"
            "At GAG 2 MM Services, we value and provide a safe and secure way to exchange your goods.\n\n"
            "**If you've found a trade and want to ensure your safety, you can use our middleman service.**\n\n"
            "**Usage Conditions:**\n"
            "• Both parties agree to trade before requesting a middleman.\n"
            "• State the trade and value.\n"
            "• Fake or troll tickets will result in punishments."
        ),
        color=EMBED_COLOR,
    )
    embed.set_footer(text="Powered by GAG 2 MM Services")
    await interaction.channel.send(embed=embed, view=TicketRequestView())
    await interaction.response.send_message("✅ Middleman panel posted.", ephemeral=True)


@bot.tree.command(name="supportpanel", description="Post the support ticket panel in this channel.")
@app_commands.checks.has_permissions(manage_guild=True)
async def supportpanel_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="GAG 2 MM Services | Support",
        description=(
            "Need help with something that isn't a trade?\n\n"
            "Click the button below to open a support ticket and a staff member "
            "will be with you shortly.\n\n"
            "**Usage Conditions:**\n"
            "• Please describe your issue clearly when opening a ticket.\n"
            "• Fake or troll tickets will result in punishments."
        ),
        color=EMBED_COLOR,
    )
    embed.set_footer(text="Powered by GAG 2 MM Services")
    await interaction.channel.send(embed=embed, view=SupportPanelView())
    await interaction.response.send_message("✅ Support panel posted.", ephemeral=True)


@bot.tree.command(name="add", description="Add a user to the current ticket.")
@app_commands.describe(user="The user to add to this ticket")
async def add_cmd(interaction: discord.Interaction, user: discord.Member):
    if not can_claim_tickets(interaction.user):
        await interaction.response.send_message(embed=error_embed("You don't have permission to do this."), ephemeral=True)
        return
    if str(interaction.channel.id) not in data_store["tickets"]:
        await interaction.response.send_message(embed=error_embed("This isn't a ticket channel."), ephemeral=True)
        return
    await interaction.channel.set_permissions(
        user, view_channel=True, send_messages=True, read_message_history=True
    )
    embed = discord.Embed(
        title="➕ User Added",
        description=f"{user.mention} has been added to this ticket by {interaction.user.mention}.",
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow(),
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="close", description="Close the current ticket.")
async def close_cmd(interaction: discord.Interaction):
    info = data_store["tickets"].get(str(interaction.channel.id))
    is_opener = info and info.get("opener_id") == interaction.user.id
    if not (can_claim_tickets(interaction.user) or is_opener):
        await interaction.response.send_message(embed=error_embed("You don't have permission to do this."), ephemeral=True)
        return
    if info is None:
        await interaction.response.send_message(embed=error_embed("This isn't a ticket channel."), ephemeral=True)
        return
    embed = discord.Embed(
        title="🔒 Closing Ticket",
        description="This ticket will close in 5 seconds...",
        color=discord.Color.red(),
    )
    await interaction.response.send_message(embed=embed)
    await close_ticket_channel(interaction.channel, interaction.user)


@bot.tree.command(name="transfer", description="Transfer this ticket's claim to another staff member.")
@app_commands.describe(user="The staff member to transfer the ticket to")
async def transfer_cmd(interaction: discord.Interaction, user: discord.Member):
    if not can_claim_tickets(interaction.user):
        await interaction.response.send_message(embed=error_embed("You don't have permission to do this."), ephemeral=True)
        return
    if not can_claim_tickets(user):
        await interaction.response.send_message(embed=error_embed(f"{user.mention} isn't middleman staff."), ephemeral=True)
        return
    info = data_store["tickets"].get(str(interaction.channel.id))
    if info is None:
        await interaction.response.send_message(embed=error_embed("This isn't a ticket channel."), ephemeral=True)
        return
    info["claimed_by"] = user.id
    save_data(data_store)
    embed = discord.Embed(
        title="🔁 Ticket Transferred",
        description=f"This ticket has been transferred to {user.mention} by {interaction.user.mention}.",
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    await interaction.response.send_message(embed=embed)


# =========================================================
#  MODERATION COMMANDS  (prefix +)
# =========================================================

BAN_COOLDOWN_SECONDS = 60 * 60  # 1 hour


async def log_command_use(ctx: commands.Context, outcome: str, detail: str = ""):
    """Logs every +command attempt (success, denial, bad usage) to the mod log."""
    embed = discord.Embed(
        title=f"🧾 Command Used: +{ctx.command.name}",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="User", value=ctx.author.mention, inline=True)
    embed.add_field(name="Outcome", value=outcome, inline=True)
    if detail:
        embed.add_field(name="Detail", value=detail, inline=False)
    await log_to_channel(ctx.guild, MOD_LOG_CHANNEL_ID, embed)


@bot.command(name="ban")
async def ban_cmd(ctx: commands.Context, member: discord.Member = None, *, reason: str = None):
    if not can_ban(ctx.author):
        await ctx.send("❌ You don't have permission to use this command.")
        await log_command_use(ctx, "❌ Denied (no permission)")
        return
    if member is None or reason is None:
        await ctx.send("⚠️ You need to provide a user and reason. Usage: `+ban @user reason`")
        await log_command_use(ctx, "⚠️ Bad usage (missing user/reason)")
        return

    uid = f"ban:{ctx.author.id}"
    now = datetime.datetime.utcnow().timestamp()
    last_used = data_store["ban_cooldowns"].get(uid, 0)
    if now - last_used < BAN_COOLDOWN_SECONDS:
        remaining = int(BAN_COOLDOWN_SECONDS - (now - last_used))
        mins, secs = divmod(remaining, 60)
        await ctx.send(f"⏳ You're on cooldown. Try again in {mins}m {secs}s.")
        await log_command_use(ctx, "⏳ Blocked (cooldown)", f"Target: {member} ({member.id})")
        return

    try:
        await member.ban(reason=f"{reason} - by {ctx.author}")
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to ban that user.")
        await log_command_use(ctx, "❌ Failed (bot missing permission)", f"Target: {member} ({member.id})")
        return

    data_store["ban_cooldowns"][uid] = now
    save_data(data_store)

    embed = discord.Embed(
        title="Member Banned",
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    await ctx.send(embed=embed)
    await log_to_channel(ctx.guild, MOD_LOG_CHANNEL_ID, embed)


@bot.command(name="unban")
async def unban_cmd(ctx: commands.Context, user_id: int = None, *, reason: str = None):
    if not can_ban(ctx.author):
        await ctx.send("❌ You don't have permission to use this command.")
        await log_command_use(ctx, "❌ Denied (no permission)")
        return
    if user_id is None or reason is None:
        await ctx.send("⚠️ You need to provide a user ID and reason. Usage: `+unban <user_id> reason`")
        await log_command_use(ctx, "⚠️ Bad usage (missing user id/reason)")
        return

    uid = f"unban:{ctx.author.id}"
    now = datetime.datetime.utcnow().timestamp()
    last_used = data_store["ban_cooldowns"].get(uid, 0)
    if now - last_used < BAN_COOLDOWN_SECONDS:
        remaining = int(BAN_COOLDOWN_SECONDS - (now - last_used))
        mins, secs = divmod(remaining, 60)
        await ctx.send(f"⏳ You're on cooldown. Try again in {mins}m {secs}s.")
        await log_command_use(ctx, "⏳ Blocked (cooldown)", f"Target ID: {user_id}")
        return

    try:
        ban_entry = await ctx.guild.fetch_ban(discord.Object(id=user_id))
    except discord.NotFound:
        await ctx.send("⚠️ That user isn't banned.")
        await log_command_use(ctx, "⚠️ Failed (user not banned)", f"Target ID: {user_id}")
        return

    try:
        await ctx.guild.unban(ban_entry.user, reason=f"{reason} - by {ctx.author}")
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to unban that user.")
        await log_command_use(ctx, "❌ Failed (bot missing permission)", f"Target: {ban_entry.user}")
        return

    data_store["ban_cooldowns"][uid] = now
    save_data(data_store)

    embed = discord.Embed(
        title="🔓 Member Unbanned",
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="User", value=f"{ban_entry.user} ({ban_entry.user.id})", inline=False)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    await ctx.send(embed=embed)
    await log_to_channel(ctx.guild, MOD_LOG_CHANNEL_ID, embed)


@bot.command(name="kick")
async def kick_cmd(ctx: commands.Context, member: discord.Member = None, *, reason: str = "No reason provided"):
    if not can_ban(ctx.author):
        await ctx.send("❌ You don't have permission to use this command.")
        await log_command_use(ctx, "❌ Denied (no permission)")
        return
    if member is None:
        await ctx.send("⚠️ You need to provide a user. Usage: `+kick @user reason`")
        await log_command_use(ctx, "⚠️ Bad usage (missing user)")
        return
    try:
        await member.kick(reason=f"{reason} - by {ctx.author}")
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to kick that user.")
        await log_command_use(ctx, "❌ Failed (bot missing permission)", f"Target: {member} ({member.id})")
        return

    embed = discord.Embed(
        title="👢 Member Kicked",
        color=discord.Color.orange(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    await ctx.send(embed=embed)
    await log_to_channel(ctx.guild, MOD_LOG_CHANNEL_ID, embed)


@bot.command(name="warn")
async def warn_cmd(ctx: commands.Context, member: discord.Member = None, *, reason: str = None):
    if not can_warn(ctx.author):
        await ctx.send("❌ You don't have permission to use this command.")
        await log_command_use(ctx, "❌ Denied (no permission)")
        return
    if member is None or reason is None:
        await ctx.send("⚠️ You need to provide a user and reason. Usage: `+warn @user reason`")
        await log_command_use(ctx, "⚠️ Bad usage (missing user/reason)")
        return

    uid = str(member.id)
    data_store["warnings"].setdefault(uid, [])
    warn_id = len(data_store["warnings"][uid]) + 1
    data_store["warnings"][uid].append(
        {
            "id": warn_id,
            "reason": reason,
            "moderator": ctx.author.id,
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }
    )
    save_data(data_store)

    embed = discord.Embed(
        title="⚠️ Member Warned",
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Warning ID", value=str(warn_id), inline=False)
    await ctx.send(embed=embed)
    await log_to_channel(ctx.guild, MOD_LOG_CHANNEL_ID, embed)

    try:
        await member.send(f"You have been warned in **{ctx.guild.name}** for: {reason}")
    except discord.Forbidden:
        pass


@bot.command(name="warnings")
async def warnings_cmd(ctx: commands.Context, member: discord.Member = None):
    if not can_warn(ctx.author):
        await ctx.send("❌ You don't have permission to use this command.")
        await log_command_use(ctx, "❌ Denied (no permission)")
        return
    if member is None:
        await ctx.send("⚠️ You need to provide a user. Usage: `+warnings @user`")
        await log_command_use(ctx, "⚠️ Bad usage (missing user)")
        return

    warns = data_store["warnings"].get(str(member.id), [])
    if not warns:
        await ctx.send(f"✅ {member.mention} has no warnings.")
        await log_command_use(ctx, "✅ Checked (no warnings)", f"Target: {member} ({member.id})")
        return

    embed = discord.Embed(title=f"Warnings for {member}", color=discord.Color.gold())
    for w in warns:
        mod = ctx.guild.get_member(w["moderator"])
        embed.add_field(
            name=f"Warning #{w['id']}",
            value=f"**Reason:** {w['reason']}\n**Moderator:** {mod.mention if mod else w['moderator']}\n**Date:** {w['timestamp'][:10]}",
            inline=False,
        )
    await ctx.send(embed=embed)

    log_embed = discord.Embed(
        title="🔍 Warnings Checked",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow(),
    )
    log_embed.add_field(name="Target", value=f"{member} ({member.id})", inline=False)
    log_embed.add_field(name="Checked by", value=ctx.author.mention, inline=False)
    await log_to_channel(ctx.guild, MOD_LOG_CHANNEL_ID, log_embed)


@bot.command(name="clearwarn")
async def clearwarn_cmd(ctx: commands.Context, member: discord.Member = None):
    if not can_warn(ctx.author):
        await ctx.send("❌ You don't have permission to use this command.")
        await log_command_use(ctx, "❌ Denied (no permission)")
        return
    if member is None:
        await ctx.send("⚠️ You need to provide a user. Usage: `+clearwarn @user`")
        await log_command_use(ctx, "⚠️ Bad usage (missing user)")
        return
    data_store["warnings"][str(member.id)] = []
    save_data(data_store)
    await ctx.send(f"✅ Cleared all warnings for {member.mention}.")

    embed = discord.Embed(
        title="🧹 Warnings Cleared",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Target", value=f"{member} ({member.id})", inline=False)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
    await log_to_channel(ctx.guild, MOD_LOG_CHANNEL_ID, embed)


@bot.command(name="delwarn")
async def delwarn_cmd(ctx: commands.Context, member: discord.Member = None, warn_id: int = None):
    if not can_warn(ctx.author):
        await ctx.send("❌ You don't have permission to use this command.")
        await log_command_use(ctx, "❌ Denied (no permission)")
        return
    if member is None or warn_id is None:
        await ctx.send("⚠️ Usage: `+delwarn @user <warning_id>`")
        await log_command_use(ctx, "⚠️ Bad usage (missing user/id)")
        return
    warns = data_store["warnings"].get(str(member.id), [])
    new_warns = [w for w in warns if w["id"] != warn_id]
    if len(new_warns) == len(warns):
        await ctx.send(f"⚠️ No warning with ID {warn_id} found for {member.mention}.")
        await log_command_use(ctx, "⚠️ Failed (warning ID not found)", f"Target: {member} ({member.id}), ID: {warn_id}")
        return
    data_store["warnings"][str(member.id)] = new_warns
    save_data(data_store)
    await ctx.send(f"✅ Deleted warning #{warn_id} for {member.mention}.")

    embed = discord.Embed(
        title="🗑️ Warning Deleted",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Target", value=f"{member} ({member.id})", inline=False)
    embed.add_field(name="Warning ID", value=str(warn_id), inline=False)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
    await log_to_channel(ctx.guild, MOD_LOG_CHANNEL_ID, embed)


# =========================================================
#  INFO / PERKS / HELP
# =========================================================

@bot.command(name="info")
async def info_cmd(ctx: commands.Context):
    embed = discord.Embed(
        title="📋 ROLE REQUIREMENTS",
        description="GAG 2 Middleman Services",
        color=EMBED_COLOR,
    )
    for role_id, req in ROLE_REQUIREMENTS:
        embed.add_field(name=ROLE_NAMES[role_id], value=req, inline=False)
    await ctx.send(embed=embed)


@bot.command(name="perks")
async def perks_cmd(ctx: commands.Context):
    embed = discord.Embed(
        title="📋 ROLE PERKS & PERMISSIONS",
        description="GAG 2 Middleman Services - Staff Role Breakdown",
        color=EMBED_COLOR,
    )
    for role_id, perk in ROLE_PERKS:
        embed.add_field(name=ROLE_NAMES[role_id], value=perk, inline=False)
    await ctx.send(embed=embed)


@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    embed = discord.Embed(title="📖 Command List", color=EMBED_COLOR)
    embed.add_field(
        name="Moderation",
        value=(
            f"`{PREFIX}ban @user reason` - ban a member (1h cooldown)\n"
            f"`{PREFIX}unban <user_id> reason` - unban a member (1h cooldown)\n"
            f"`{PREFIX}kick @user reason` - kick a member\n"
            f"`{PREFIX}warn @user reason` - warn a member\n"
            f"`{PREFIX}warnings @user` - view a member's warnings\n"
            f"`{PREFIX}clearwarn @user` - clear all warnings\n"
            f"`{PREFIX}delwarn @user id` - delete a specific warning"
        ),
        inline=False,
    )
    embed.add_field(
        name="Info",
        value=(
            f"`{PREFIX}info` - view role requirements\n"
            f"`{PREFIX}perks` - view role perks & permissions\n"
            f"`{PREFIX}help` - view this menu"
        ),
        inline=False,
    )
    embed.add_field(
        name="Tickets (slash commands)",
        value=(
            "`/middleman` - post the middleman request panel\n"
            "`/supportpanel` - post the support ticket panel\n"
            "`/add @user` - add a user to the current ticket\n"
            "`/close` - close the current ticket\n"
            "`/transfer @user` - transfer ticket claim"
        ),
        inline=False,
    )
    embed.add_field(
        name="Roles (slash commands)",
        value="`/managerole add|remove @user role reason` - manage a member's rank",
        inline=False,
    )
    embed.add_field(
        name="Trading (slash commands)",
        value=(
            "`/offer @user` - send a scam offer (posted in-channel)\n"
            "`/about` `/faq` `/tos` `/scamawareness` - server info"
        ),
        inline=False,
    )
    await ctx.send(embed=embed)


# =========================================================
#  /managerole
# =========================================================

@bot.tree.command(name="managerole", description="Add or remove a staff role from a user.")
@app_commands.describe(action="add or remove", user="The user to update", role="The role to add/remove", reason="Reason for this change")
@app_commands.choices(action=[
    app_commands.Choice(name="add", value="add"),
    app_commands.Choice(name="remove", value="remove"),
])
async def managerole_cmd(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    user: discord.Member,
    role: discord.Role,
    reason: str,
):
    if not can_manage_roles(interaction.user):
        await interaction.response.send_message(embed=error_embed("You don't have permission to use this command."), ephemeral=True)
        return

    if role.id not in ROLE_HIERARCHY:
        await interaction.response.send_message(embed=error_embed("That isn't a managed staff role."), ephemeral=True)
        return

    # A staff member can only manage roles below their own rank.
    actor_level = member_role_level(interaction.user)
    target_role_level = ROLE_HIERARCHY.index(role.id)
    if target_role_level >= actor_level and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            embed=error_embed("You can only manage roles below your own rank."), ephemeral=True
        )
        return

    if action.value == "add":
        await user.add_roles(role, reason=f"{reason} - by {interaction.user}")
        verb = "added to"
    else:
        await user.remove_roles(role, reason=f"{reason} - by {interaction.user}")
        verb = "removed from"

    embed = discord.Embed(
        title="🏷️ Role Updated",
        description=f"**{role.name}** was {verb} {user.mention}",
        color=ACCENT_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Staff", value=interaction.user.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=True)
    await interaction.response.send_message(embed=embed)
    await log_to_channel(interaction.guild, ROLE_LOG_CHANNEL_ID, embed)


# =========================================================
#  TRADE OFFER FLOW  (/offer, /explain)
# =========================================================

class OfferView(discord.ui.View):
    def __init__(self, target: discord.Member):
        super().__init__(timeout=300)
        self.target = target

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, custom_id="offer:accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(embed=error_embed("This offer isn't for you."), ephemeral=True)
            return
        role = interaction.guild.get_role(ROLE_GIVEAWAY_PING) if interaction.guild else None
        if role and isinstance(interaction.user, discord.Member):
            try:
                await interaction.user.add_roles(role, reason="Accepted trader offer")
            except discord.Forbidden:
                pass
        for child in self.children:
            child.disabled = True
        embed = discord.Embed(
            title="Offer Accepted",
            description=f"{self.target.mention} has accepted the offer and has joined us.!",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red, custom_id="offer:decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(embed=error_embed("This offer isn't for you."), ephemeral=True)
            return
        for child in self.children:
            child.disabled = True
        embed = discord.Embed(
            title="Offer Declined",
            description=f"{self.target.mention} has declined the offer.",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="offer", description="Send a trade offer to a user.")
@app_commands.describe(user="The user to offer a trade to")
async def offer_cmd(interaction: discord.Interaction, user: discord.Member):
    if user.bot:
        await interaction.response.send_message(
            embed=error_embed("You can't send a trade offer to a bot."),
            ephemeral=True
        )
        return

    if user.id == interaction.user.id:
        await interaction.response.send_message(
            embed=error_embed("You can't send a trade offer to yourself."),
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="Scam Offer",
        description=f"""
{user.mention},

 You've Been Scammed – But This Is Your Turning Point.

We know exactly how you feel right now. Frustrated. Angry. Maybe even defeated. We've all been there. Every single one of us standing here today has been in your shoes.

But here's the truth: getting scammed isn't the end of your story – it's the beginning of a better one.

What if we told you that losing today could be the best thing that ever happened to you?

Here's the reality:
You can either dwell on what happened and stay stuck in the past, OR you can take control, flip the script, and turn this loss into your biggest come back.

How does this work?
We take what happened, we learn from it, we move forward, and we start building real profit. You'll be working alongside experienced middlemen who know exactly how to play the game. Together, you'll split profits 50/50 and turn your loss into a win.

This isn't about revenge. This isn't about being bitter. This is about leveling up.

You've got 85 seconds. The past is gone. The future is waiting.

Make the right choice. Accept your comeback.
""",
        color=ACCENT_COLOR,
        timestamp=discord.utils.utcnow(),
    )

    embed.set_footer(text=f"Offered by {interaction.user}")

    await interaction.response.send_message(
        content=user.mention,
        embed=embed,
        view=OfferView(user)
    )


class ExplainStep2View(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    @discord.ui.button(label="Next Step", style=discord.ButtonStyle.blurple)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(embed=error_embed("This isn't your session."), ephemeral=True)
            return
embed = discord.Embed(
    title="📈 Step 3 of 3: How to Make Profit",
    description="There are two ways to start making profit:\n\n"
                "**1. Split with the Middleman** – You and the middleman split the profits 50/50 on every successful trade.\n\n"
                "**2. Become a Middleman** – Once you reach 5 successful hits, you unlock the Middleman role and can run your own trades for even bigger profits.\n\n"
                "**That's it. Simple, repeatable, and profitable.**\n\n"
                "Good luck — you've got this!",
    color=ACCENT_COLOR,
)
        )
        await interaction.response.edit_message(embed=embed, view=None)


class ExplainStep1View(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    @discord.ui.button(label="Next Step", style=discord.ButtonStyle.blurple)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(embed=error_embed("This isn't your session."), ephemeral=True)
            return
        embed = discord.Embed(
            title="Step 2 of 3",
            description=(
                "Once the trade is confirmed, click the Request Middleman button to continue."

                "Once you've done that, you and the middleman will work together to secure the profits and split them 50/50."
            ),
            color=ACCENT_COLOR,
        )
        await interaction.response.edit_message(embed=embed, view=ExplainStep2View(self.owner_id))


class ExplainYesNoView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(embed=error_embed("This isn't your session."), ephemeral=True)
            return
        embed = discord.Embed(
            title="Step 1 of 3",
            description=(
                "Heres how to start, First Go to 4-5 servers and type a trade to lure victims in., "
                "Make sure to not overpay too much, otherwise they will gain suspicion."
            ),
            color=ACCENT_COLOR,
        )
        await interaction.response.edit_message(embed=embed, view=ExplainStep1View(self.owner_id))

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(embed=error_embed("This isn't your session."), ephemeral=True)
            return
        embed = discord.Embed(description="Okay, no worries! Come back anytime.", color=discord.Color.light_grey())
        await interaction.response.edit_message(embed=embed, view=None)


class ExplainPanelView(discord.ui.View):
    """Persistent panel posted with /explain. Anyone can click it to start their own private walkthrough."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Learn How To Trade",
        emoji="📚",
        style=discord.ButtonStyle.blurple,
        custom_id="explain:learn",
    )
    async def learn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Learn How To Hit",
            description="Would you like to learn how to start hitting??",
            color=ACCENT_COLOR,
        )
        await interaction.response.send_message(
            embed=embed, view=ExplainYesNoView(interaction.user.id), ephemeral=True
        )


@bot.tree.command(name="explain", description="Post the 'learn how to trade' panel in this channel.")
@app_commands.checks.has_permissions(manage_guild=True)
async def explain_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 Hitting Guide",
        description=(
            "New to Hitting? Click the button below for a quick walkthrough on how "
            "to make successful hits."
        ),
        color=ACCENT_COLOR,
    )
    embed.set_footer(text="Powered by GAG 2 MM Services")
    await interaction.channel.send(embed=embed, view=ExplainPanelView())
    await interaction.response.send_message("✅ Trading guide panel posted.", ephemeral=True)



# =========================================================
#  INFO / FAQ / TOS / SCAM AWARENESS
# =========================================================

@bot.tree.command(name="about", description="Learn about Levi's MM Services.")
async def about_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Levi's MM Services",
        description=(
            "A dedicated, staff-run middleman service built to keep trades safe, "
            "transparent, and fair for everyone involved."
        ),
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="🛡️ Our Mission",
        value=(
            "We exist to eliminate scams from trading by placing a trained, "
            "vetted middleman between both parties for every deal."
        ),
        inline=False,
    )
    embed.add_field(
        name="👥 Our Staff",
        value=(
            "Every staff member earns their rank through proven experience and "
            "is held to strict conduct standards. Use `+info` to see rank "
            "requirements and `+perks` for permissions per rank."
        ),
        inline=False,
    )
    embed.add_field(
        name="💰 Cost",
        value="Our core middleman service is completely free to use.",
        inline=True,
    )
    embed.add_field(
        name="⏱️ Availability",
        value="Staff respond to tickets as quickly as possible around the clock.",
        inline=True,
    )
    if interaction.guild and interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)
    embed.set_footer(text="Levi's MM Services • Use /faq /tos /scamawareness for more info")
    embed.timestamp = discord.utils.utcnow()
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="faq", description="Frequently asked questions.")
async def faq_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Frequently Asked Questions",
        description="Answers to the questions we get asked most.",
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="How do I request a middleman?",
        value="Click **Request Middleman** on the ticket panel and complete the short form. A ticket will be created automatically.",
        inline=False,
    )
    embed.add_field(
        name="Is the middleman service free?",
        value="Yes — our middleman service is completely free for all users.",
        inline=False,
    )
    embed.add_field(
        name="How long will I wait for a middleman?",
        value="Response times vary with staff availability, but tickets are typically picked up quickly. Please be patient after opening one.",
        inline=False,
    )
    embed.add_field(
        name="How do I become a middleman?",
        value="Have 5 completed trades, via our middleman and also provide collat.",
        inline=False,
    )
    embed.add_field(
        name="What happens if the other party doesn't cooperate?",
        value="Notify the middleman handling your ticket immediately — they are trained to handle disputes and non-cooperation.",
        inline=False,
    )
    embed.add_field(
        name="Can I request a specific middleman?",
        value="You can ask in your ticket, but assignment ultimately depends on staff availability.",
        inline=False,
    )
    embed.set_footer(text="GAG 2 MM Services • Still have questions? Open a support ticket")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="tos", description="Terms of Service.")
async def tos_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Terms of Service",
        description="By using our middleman service, you agree to the following terms.",
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="1. Mutual Agreement",
        value="Both parties must agree to the trade before a middleman is requested.",
        inline=False,
    )
    embed.add_field(
        name="2. Accurate Information",
        value="You must clearly and honestly state the trade and its value when opening a ticket.",
        inline=False,
    )
    embed.add_field(
        name="3. No Fake or Troll Tickets",
        value="Wasting staff time with fake, joke, or troll tickets will result in punishment.",
        inline=False,
    )
    embed.add_field(
        name="4. Staff Authority",
        value="Staff decisions during a trade dispute are final and must be respected.",
        inline=False,
    )
    embed.add_field(
        name="5. Zero Tolerance for Scamming",
        value="Any attempt to scam another user through our service will result in an immediate, permanent ban.",
        inline=False,
    )
    embed.add_field(
        name="6. Server Rules Apply",
        value="You agree to follow all server rules and staff instructions for the duration of your trade.",
        inline=False,
    )
    embed.set_footer(text="GAG 2 MM Services • Terms of Service")
    embed.timestamp = discord.utils.utcnow()
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="scamawareness", description="Scam awareness tips.")
async def scamawareness_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🚨 Scam Awareness",
        description="Trading always carries risk. Follow these guidelines to keep yourself protected.",
        color=discord.Color.red(),
    )
    embed.add_field(
        name="Always Use a Middleman",
        value="For any trade of meaningful value, use our free middleman service rather than trading directly.",
        inline=False,
    )
    embed.add_field(
        name="Never Share Sensitive Info",
        value="Never give out your password, login links, authenticator codes, or 2FA codes to anyone — including staff.",
        inline=False,
    )
    embed.add_field(
        name="Too Good To Be True?",
        value="Be suspicious of offers that seem unusually generous or urgent — that pressure is a common scam tactic.",
        inline=False,
    )
    embed.add_field(
        name="Verify Who You're Trading With",
        value="Double-check usernames, IDs, and profiles before confirming any trade, even with someone who seems familiar.",
        inline=False,
    )
    embed.add_field(
        name="Report Suspicious Activity",
        value="If something feels off, stop the trade and report it to staff immediately — don't wait until after the fact.",
        inline=False,
    )
    embed.set_footer(text="GAG 2 MM Services • Stay safe, trade smart")
    await interaction.response.send_message(embed=embed)


# =========================================================
#  EVENTS
# =========================================================

@bot.event
async def on_ready():
    bot.add_view(TicketRequestView())
    bot.add_view(SupportPanelView())
    bot.add_view(TicketControlView())
    bot.add_view(ExplainPanelView())
    try:
        if GUILD_ID:
            guild_obj = discord.Object(id=GUILD_ID)
            bot.tree.copy_global_to(guild=guild_obj)
            synced = await bot.tree.sync(guild=guild_obj)
        else:
            synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"Slash sync failed: {e}")
    print(f"Logged in as {bot.user} ({bot.user.id})")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "❌ You don't have permission to use this command."
    else:
        msg = "⚠️ Something went wrong running that command. Please try again."
        print(f"Slash command error: {error}")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except discord.HTTPException:
        pass


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MemberNotFound):
        await ctx.send("⚠️ I couldn't find that member.")
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("⚠️ You're missing an argument for that command. Use `+help` to see usage.")
        return
    raise error


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN is missing. Set it in your .env / Railway variables.")
    bot.run(TOKEN)
