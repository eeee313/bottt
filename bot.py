"""
BloxTrades / Levi's Middleman Services - Discord Bot
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
SUPPORT_TICKET_CATEGORY_ID = 1528491782491345107   # /support ticket category

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
    embed.set_footer(text="Thank you for keeping your trade safe, smooth, and secure! • BloxTrades")
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

        channel = await guild.create_text_channel(
            channel_name, category=category, overwrites=overwrites
        )

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

        channel = await guild.create_text_channel(
            channel_name, category=category, overwrites=overwrites
        )

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
        embed.set_footer(text="A staff member will be with you shortly • BloxTrades")

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
        emoji="🛠️",
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
                "❌ You don't have permission to claim tickets.", ephemeral=True
            )
            return
        info = data_store["tickets"].get(str(interaction.channel.id))
        if info is None:
            await interaction.response.send_message("⚠️ This isn't a tracked ticket.", ephemeral=True)
            return
        if info.get("claimed_by"):
            claimer = interaction.guild.get_member(info["claimed_by"])
            await interaction.response.send_message(
                f"⚠️ Already claimed by {claimer.mention if claimer else 'someone'}.", ephemeral=True
            )
            return
        info["claimed_by"] = interaction.user.id
        save_data(data_store)
        await interaction.response.send_message(f"✅ Ticket claimed by {interaction.user.mention}.")

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.gray, custom_id="ticket:unclaim")
    async def unclaim(self, interaction: discord.Interaction, button: discord.ui.Button):
        info = data_store["tickets"].get(str(interaction.channel.id))
        if info is None:
            await interaction.response.send_message("⚠️ This isn't a tracked ticket.", ephemeral=True)
            return
        if info.get("claimed_by") != interaction.user.id and not can_manage_roles(interaction.user):
            await interaction.response.send_message(
                "❌ Only the staff member who claimed this ticket can unclaim it.", ephemeral=True
            )
            return
        info["claimed_by"] = None
        save_data(data_store)
        await interaction.response.send_message("↩️ Ticket unclaimed.")

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red, custom_id="ticket:close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        info = data_store["tickets"].get(str(interaction.channel.id))
        is_opener = info and info.get("opener_id") == interaction.user.id
        if not (can_claim_tickets(interaction.user) or is_opener):
            await interaction.response.send_message(
                "❌ You don't have permission to close this ticket.", ephemeral=True
            )
            return
        await interaction.response.send_message("🔒 Closing ticket in 5 seconds...")
        await close_ticket_channel(interaction.channel, interaction.user)


async def close_ticket_channel(channel: discord.TextChannel, closer: discord.Member):
    """Builds a simple text transcript, posts it to the transcripts channel, then deletes the ticket."""
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

    embed = discord.Embed(
        title="📁 Ticket Closed",
        description=f"**Ticket:** {channel.name}\n**Opened by:** {opener.mention if opener else 'Unknown'}\n**Closed by:** {closer.mention}",
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow(),
    )
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

@bot.tree.command(name="support", description="Post the support ticket panel in this channel.")
@app_commands.checks.has_permissions(manage_guild=True)
async def support_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="bloxtrades | MM Service",
        description=(
            "Welcome to our middleman Service centre.\n\n"
            "At bloxtrades, we value and provide a safe and secure way to exchange your goods.\n\n"
            "**If you've found a trade and want to ensure your safety, you can use our middleman service.**\n\n"
            "**Usage Conditions:**\n"
            "• Both parties agree to trade before requesting a middleman.\n"
            "• State the trade and value.\n"
            "• Fake or troll tickets will result in punishments."
        ),
        color=EMBED_COLOR,
    )
    embed.set_footer(text="Powered by bloxtrades")
    await interaction.channel.send(embed=embed, view=TicketRequestView())
    await interaction.response.send_message("✅ Support panel posted.", ephemeral=True)


@bot.tree.command(name="add", description="Add a user to the current ticket.")
@app_commands.describe(user="The user to add to this ticket")
async def add_cmd(interaction: discord.Interaction, user: discord.Member):
    if not can_claim_tickets(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    if str(interaction.channel.id) not in data_store["tickets"]:
        await interaction.response.send_message("⚠️ This isn't a ticket channel.", ephemeral=True)
        return
    await interaction.channel.set_permissions(
        user, view_channel=True, send_messages=True, read_message_history=True
    )
    await interaction.response.send_message(f"✅ Added {user.mention} to the ticket.")


@bot.tree.command(name="close", description="Close the current ticket.")
async def close_cmd(interaction: discord.Interaction):
    info = data_store["tickets"].get(str(interaction.channel.id))
    is_opener = info and info.get("opener_id") == interaction.user.id
    if not (can_claim_tickets(interaction.user) or is_opener):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    if info is None:
        await interaction.response.send_message("⚠️ This isn't a ticket channel.", ephemeral=True)
        return
    await interaction.response.send_message("🔒 Closing ticket in 5 seconds...")
    await close_ticket_channel(interaction.channel, interaction.user)


@bot.tree.command(name="transfer", description="Transfer this ticket's claim to another staff member.")
@app_commands.describe(user="The staff member to transfer the ticket to")
async def transfer_cmd(interaction: discord.Interaction, user: discord.Member):
    if not can_claim_tickets(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to do this.", ephemeral=True)
        return
    if not can_claim_tickets(user):
        await interaction.response.send_message(f"❌ {user.mention} isn't middleman staff.", ephemeral=True)
        return
    info = data_store["tickets"].get(str(interaction.channel.id))
    if info is None:
        await interaction.response.send_message("⚠️ This isn't a ticket channel.", ephemeral=True)
        return
    info["claimed_by"] = user.id
    save_data(data_store)
    await interaction.response.send_message(f"🔁 Ticket transferred to {user.mention}.")


# =========================================================
#  MODERATION COMMANDS  (prefix +)
# =========================================================

BAN_COOLDOWN_SECONDS = 30 * 60  # 30 minutes


@bot.command(name="ban")
async def ban_cmd(ctx: commands.Context, member: discord.Member = None, *, reason: str = None):
    if not can_ban(ctx.author):
        await ctx.send("❌ You don't have permission to use this command.")
        return
    if member is None or reason is None:
        await ctx.send("⚠️ You need to provide a user and reason. Usage: `+ban @user reason`")
        return

    uid = str(ctx.author.id)
    now = datetime.datetime.utcnow().timestamp()
    last_used = data_store["ban_cooldowns"].get(uid, 0)
    if now - last_used < BAN_COOLDOWN_SECONDS:
        remaining = int(BAN_COOLDOWN_SECONDS - (now - last_used))
        mins, secs = divmod(remaining, 60)
        await ctx.send(f"⏳ You're on cooldown. Try again in {mins}m {secs}s.")
        return

    try:
        await member.ban(reason=f"{reason} - by {ctx.author}")
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to ban that user.")
        return

    data_store["ban_cooldowns"][uid] = now
    save_data(data_store)

    embed = discord.Embed(
        title="🔨 Member Banned",
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    await ctx.send(embed=embed)
    await log_to_channel(ctx.guild, MOD_LOG_CHANNEL_ID, embed)


@bot.command(name="kick")
async def kick_cmd(ctx: commands.Context, member: discord.Member = None, *, reason: str = "No reason provided"):
    if not can_ban(ctx.author):
        await ctx.send("❌ You don't have permission to use this command.")
        return
    if member is None:
        await ctx.send("⚠️ You need to provide a user. Usage: `+kick @user reason`")
        return
    try:
        await member.kick(reason=f"{reason} - by {ctx.author}")
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to kick that user.")
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
        return
    if member is None or reason is None:
        await ctx.send("⚠️ You need to provide a user and reason. Usage: `+warn @user reason`")
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
        return
    if member is None:
        await ctx.send("⚠️ You need to provide a user. Usage: `+warnings @user`")
        return

    warns = data_store["warnings"].get(str(member.id), [])
    if not warns:
        await ctx.send(f"✅ {member.mention} has no warnings.")
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


@bot.command(name="clearwarn")
async def clearwarn_cmd(ctx: commands.Context, member: discord.Member = None):
    if not can_warn(ctx.author):
        await ctx.send("❌ You don't have permission to use this command.")
        return
    if member is None:
        await ctx.send("⚠️ You need to provide a user. Usage: `+clearwarn @user`")
        return
    data_store["warnings"][str(member.id)] = []
    save_data(data_store)
    await ctx.send(f"✅ Cleared all warnings for {member.mention}.")


@bot.command(name="delwarn")
async def delwarn_cmd(ctx: commands.Context, member: discord.Member = None, warn_id: int = None):
    if not can_warn(ctx.author):
        await ctx.send("❌ You don't have permission to use this command.")
        return
    if member is None or warn_id is None:
        await ctx.send("⚠️ Usage: `+delwarn @user <warning_id>`")
        return
    warns = data_store["warnings"].get(str(member.id), [])
    new_warns = [w for w in warns if w["id"] != warn_id]
    if len(new_warns) == len(warns):
        await ctx.send(f"⚠️ No warning with ID {warn_id} found for {member.mention}.")
        return
    data_store["warnings"][str(member.id)] = new_warns
    save_data(data_store)
    await ctx.send(f"✅ Deleted warning #{warn_id} for {member.mention}.")


# =========================================================
#  INFO / PERKS / HELP
# =========================================================

@bot.command(name="info")
async def info_cmd(ctx: commands.Context):
    embed = discord.Embed(
        title="📋 ROLE REQUIREMENTS",
        description="Levi's Middleman Services",
        color=EMBED_COLOR,
    )
    for role_id, req in ROLE_REQUIREMENTS:
        embed.add_field(name=ROLE_NAMES[role_id], value=req, inline=False)
    await ctx.send(embed=embed)


@bot.command(name="perks")
async def perks_cmd(ctx: commands.Context):
    embed = discord.Embed(
        title="📋 ROLE PERKS & PERMISSIONS",
        description="Levi's Middleman Services - Staff Role Breakdown",
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
            f"`{PREFIX}ban @user reason` - ban a member (30m cooldown)\n"
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
            "`/support` - post the support panel\n"
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
            "`/offer @user` - send a trade offer\n"
            "`/explain` - learn how to make the best trades\n"
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
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    if role.id not in ROLE_HIERARCHY:
        await interaction.response.send_message("⚠️ That isn't a managed staff role.", ephemeral=True)
        return

    # A staff member can only manage roles below their own rank.
    actor_level = member_role_level(interaction.user)
    target_role_level = ROLE_HIERARCHY.index(role.id)
    if target_role_level >= actor_level and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ You can only manage roles below your own rank.", ephemeral=True
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
            await interaction.response.send_message("This offer isn't for you.", ephemeral=True)
            return
        role = interaction.guild.get_role(ROLE_GIVEAWAY_PING) if interaction.guild else None
        if role and isinstance(interaction.user, discord.Member):
            try:
                await interaction.user.add_roles(role, reason="Accepted trader offer")
            except discord.Forbidden:
                pass
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="🎉 Great, you have accepted to become a trader!", view=self
        )

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red, custom_id="offer:decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("This offer isn't for you.", ephemeral=True)
            return
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="You have declined the offer.", view=self)


@bot.tree.command(name="offer", description="Send a trade offer to a user.")
@app_commands.describe(user="The user to offer a trade to")
async def offer_cmd(interaction: discord.Interaction, user: discord.Member):
    embed = discord.Embed(
        title="You have been offered a trade!",
        description="How will you accept? I will tend for you to accept this trade, to make more, etc.",
        color=ACCENT_COLOR,
    )
    try:
        await user.send(embed=embed, view=OfferView(user))
        await interaction.response.send_message(f"✅ Offer sent to {user.mention}.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(
            f"⚠️ Couldn't DM {user.mention}, their DMs may be closed.", ephemeral=True
        )


class ExplainStep2View(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    @discord.ui.button(label="Next Step", style=discord.ButtonStyle.blurple)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This isn't your session.", ephemeral=True)
            return
        embed = discord.Embed(
            title="Step 3",
            description="All done, good luck!",
            color=ACCENT_COLOR,
        )
        await interaction.response.edit_message(embed=embed, view=None)


class ExplainStep1View(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    @discord.ui.button(label="Next Step", style=discord.ButtonStyle.blurple)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This isn't your session.", ephemeral=True)
            return
        embed = discord.Embed(
            title="Step 2",
            description=(
                "Once you have a confirmed trade, make sure to tell them to use a "
                "middleman, to keep the trade safe and secure."
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
            await interaction.response.send_message("This isn't your session.", ephemeral=True)
            return
        embed = discord.Embed(
            title="Step 1",
            description=(
                "Great, go to other servers and find trades. Once you have a trade, "
                "make sure it's confirmed."
            ),
            color=ACCENT_COLOR,
        )
        await interaction.response.edit_message(embed=embed, view=ExplainStep1View(self.owner_id))

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This isn't your session.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Okay, no worries!", embed=None, view=None)


@bot.tree.command(name="explain", description="Learn how to make the best trades.")
async def explain_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Would you like to learn how to make the best trades?",
        view=ExplainYesNoView(interaction.user.id),
        ephemeral=True,
    )


# =========================================================
#  INFO / FAQ / TOS / SCAM AWARENESS
# =========================================================

@bot.tree.command(name="about", description="Learn about BloxTrades.")
async def about_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="ℹ️ About BloxTrades",
        description=(
            "BloxTrades is a trusted trading community offering a professional, "
            "secure middleman service to protect both parties of a trade.\n\n"
            "Our staff team is trained, ranked, and held to strict standards to "
            "ensure every trade is handled safely and fairly."
        ),
        color=EMBED_COLOR,
    )
    embed.set_footer(text="Powered by bloxtrades")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="faq", description="Frequently asked questions.")
async def faq_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="❓ Frequently Asked Questions", color=EMBED_COLOR)
    embed.add_field(
        name="How do I request a middleman?",
        value="Use the **Request Middleman** button on the ticket panel and fill out the form.",
        inline=False,
    )
    embed.add_field(
        name="Is the middleman service free?",
        value="Yes, our middleman service is completely free to use.",
        inline=False,
    )
    embed.add_field(
        name="How do I become staff?",
        value="Check `/managerole` requirements with the `+info` command.",
        inline=False,
    )
    embed.add_field(
        name="What if the other party doesn't cooperate?",
        value="Let the middleman know immediately in your ticket, and they will handle it accordingly.",
        inline=False,
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="tos", description="Terms of Service.")
async def tos_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📜 Terms of Service",
        description=(
            "1. Both parties must agree to a trade before requesting a middleman.\n"
            "2. Fake, troll, or wasted tickets will result in punishment.\n"
            "3. Staff decisions during a trade dispute are final.\n"
            "4. Any attempt to scam another user will result in an immediate ban.\n"
            "5. By using this service, you agree to follow all server rules and "
            "staff instructions during your trade."
        ),
        color=EMBED_COLOR,
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="scamawareness", description="Scam awareness tips.")
async def scamawareness_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🚨 Scam Awareness",
        description=(
            "Protect yourself when trading:\n\n"
            "• Never trade without a middleman for higher-value deals.\n"
            "• Never share your password, login link, or 2FA codes with anyone.\n"
            "• Be cautious of deals that sound too good to be true.\n"
            "• Always double check who you're trading with before confirming.\n"
            "• Report any suspicious activity to staff immediately."
        ),
        color=discord.Color.red(),
    )
    await interaction.response.send_message(embed=embed)


# =========================================================
#  EVENTS
# =========================================================

@bot.event
async def on_ready():
    bot.add_view(TicketRequestView())
    bot.add_view(SupportPanelView())
    bot.add_view(TicketControlView())
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
