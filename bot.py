import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime
import asyncio
import os

print("=== LEVI'S MIDDLEMAN BOT STARTING ===")
print(f"Python version: {os.sys.version}")
print(f"Token exists: {bool(os.getenv('DISCORD_TOKEN'))}")

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('middleman.db')
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                moderator_id INTEGER,
                reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER,
                user_id INTEGER,
                middleman_id INTEGER,
                status TEXT DEFAULT 'open',
                ticket_type TEXT DEFAULT 'middleman',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                closed_at DATETIME
            )
        ''')
        try:
            self.cursor.execute("ALTER TABLE tickets ADD COLUMN ticket_type TEXT DEFAULT 'middleman'")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS vouches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                vouch_count INTEGER DEFAULT 0
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS hits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                hit_count INTEGER DEFAULT 0
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS mercy_users (
                user_id INTEGER PRIMARY KEY,
                accepted_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def add_warning(self, user_id, moderator_id, reason):
        self.cursor.execute("INSERT INTO warnings (user_id, moderator_id, reason) VALUES (?, ?, ?)", (user_id, moderator_id, reason))
        self.conn.commit()
        return self.cursor.lastrowid

    def get_warnings(self, user_id):
        self.cursor.execute("SELECT id, moderator_id, reason, timestamp FROM warnings WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
        return self.cursor.fetchall()

    def clear_warnings(self, user_id):
        self.cursor.execute("DELETE FROM warnings WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def delete_warning(self, warning_id):
        self.cursor.execute("DELETE FROM warnings WHERE id = ?", (warning_id,))
        self.conn.commit()

    def add_vouch(self, user_id):
        self.cursor.execute("INSERT INTO vouches (user_id, vouch_count) VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET vouch_count = vouch_count + 1", (user_id,))
        self.conn.commit()

    def get_vouch_count(self, user_id):
        self.cursor.execute("SELECT vouch_count FROM vouches WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0

    def remove_vouches(self, user_id, count=0):
        if count > 0:
            self.cursor.execute("UPDATE vouches SET vouch_count = vouch_count - ? WHERE user_id = ?", (count, user_id))
        else:
            self.cursor.execute("DELETE FROM vouches WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def add_hit(self, user_id):
        self.cursor.execute("INSERT INTO hits (user_id, hit_count) VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET hit_count = hit_count + 1", (user_id,))
        self.conn.commit()
        return self.get_hit_count(user_id)

    def get_hit_count(self, user_id):
        self.cursor.execute("SELECT hit_count FROM hits WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0

    def add_mercy_user(self, user_id):
        self.cursor.execute("INSERT OR IGNORE INTO mercy_users (user_id) VALUES (?)", (user_id,))
        self.conn.commit()

    def is_mercy_user(self, user_id):
        self.cursor.execute("SELECT user_id FROM mercy_users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone() is not None

    def create_ticket(self, channel_id, user_id, ticket_type='middleman'):
        self.cursor.execute("INSERT INTO tickets (channel_id, user_id, ticket_type) VALUES (?, ?, ?)", (channel_id, user_id, ticket_type))
        self.conn.commit()
        return self.cursor.lastrowid

    def get_open_ticket(self, user_id, ticket_type='middleman'):
        self.cursor.execute("SELECT channel_id FROM tickets WHERE user_id = ? AND status = 'open' AND ticket_type = ?", (user_id, ticket_type))
        return self.cursor.fetchone()

    def claim_ticket(self, channel_id, middleman_id):
        self.cursor.execute("UPDATE tickets SET middleman_id = ? WHERE channel_id = ? AND status = 'open'", (middleman_id, channel_id))
        self.conn.commit()

    def get_ticket(self, channel_id):
        self.cursor.execute("SELECT user_id, middleman_id, status, ticket_type FROM tickets WHERE channel_id = ?", (channel_id,))
        return self.cursor.fetchone()

class MiddlemanBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        super().__init__(command_prefix='+', intents=intents)
        self.db = Database()
        self.role_ids = {
            'Giveaway Pings': 1528463410562601131,
            'Trial Middleman': 1528463468737466469,
            'Middleman': 1528463607543894067,
            'Lead Middleman': 1528463688154218618,
            'Moderator': 1528463980329439325,
            'Coordinator': 1528465524424573149,
            'Overseer': 1528465730176290857,
            'Head of Management': 1528465890302230618,
            'Head of Coordination': 1528466122238591198,
            'Head of Operations': 1528466496890605660,
            'Head of Dev': 1528466008170303559,
            'Head of Staff': 1528466750956376094,
            'President': 1528466975464882290,
            'Setup Role': 1526271680371232788,
            'Auto Role Member': 1526273333811876071
        }
        self.role_requirements = {
            'Trial Middleman': {'hits': 5, 'price': 5},
            'Middleman': {'hits': 10, 'price': 10, 'discount': 5},
            'Lead Middleman': {'hits': 20, 'price': 15, 'discount': 7},
            'Moderator': {'hits': 30, 'price': 25, 'discount': 10},
            'Coordinator': {'hits': 50, 'price': 25, 'discount': 15},
            'Overseer': {'price': 40, 'discount': 25},
            'Head of Management': {'price': 50, 'discount': 30},
            'Head of Coordination': {'price': 60, 'discount': 35},
            'Head of Operations': {'price': 75, 'discount': 45},
            'Head of Dev': {'price': 100, 'discount': 60},
            'Head of Staff': {'price': 150, 'discount': 75},
            'President': {'price': 250, 'discount': 100}
        }
        self.permission_levels = {
            'Trial Middleman': 1, 'Middleman': 2, 'Lead Middleman': 3,
            'Moderator': 4, 'Coordinator': 5, 'Overseer': 6,
            'Head of Management': 7, 'Head of Coordination': 8,
            'Head of Operations': 9, 'Head of Dev': 10,
            'Head of Staff': 11, 'President': 12
        }
        self.support_channel = 1528462676446023841
        self.support_category = 1528491782491345107
        self.general_support_category = 1528491782491345107
        self.middleman_category = 1527856283498184876
        self.welcome_channel = 1527829658979012608
        self.setup_role = 1526271680371232788
        self.middleman_staff_roles = [
            'Trial Middleman', 'Middleman', 'Lead Middleman',
            'Moderator', 'Coordinator', 'Overseer',
            'Head of Management', 'Head of Coordination', 'Head of Operations',
            'Head of Staff', 'President'
        ]
        self.support_staff_roles = [
            'Moderator', 'Coordinator', 'Overseer',
            'Head of Management', 'Head of Coordination', 'Head of Operations',
            'Head of Staff', 'President'
        ]

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Slash commands synced!")

    def has_permission(self, user, required_roles):
        if not isinstance(user, discord.Member):
            return False
        for role in user.roles:
            for req_role in required_roles:
                if req_role in self.role_ids and role.id == self.role_ids[req_role]:
                    return True
        return False

    def has_setup_role(self, user):
        if not isinstance(user, discord.Member):
            return False
        return any(role.id == self.setup_role for role in user.roles)

    def has_middleman_permission(self, user):
        if not isinstance(user, discord.Member):
            return False
        return self.has_permission(user, self.middleman_staff_roles)

    def has_support_permission(self, user):
        if not isinstance(user, discord.Member):
            return False
        return self.has_permission(user, self.support_staff_roles)

    def can_manage_role(self, user, role):
        if not isinstance(user, discord.Member):
            return False
        user_highest = 0
        role_position = 0
        for r in user.roles:
            if r.id in self.role_ids.values():
                for name, rid in self.role_ids.items():
                    if rid == r.id and name in self.permission_levels:
                        if self.permission_levels[name] > user_highest:
                            user_highest = self.permission_levels[name]
        for name, rid in self.role_ids.items():
            if rid == role.id and name in self.permission_levels:
                role_position = self.permission_levels[name]
                break
        return user_highest > role_position

    def is_ticket_channel(self, channel):
        if not channel:
            return False
        self.db.cursor.execute("SELECT id FROM tickets WHERE channel_id = ? AND status = 'open'", (channel.id,))
        return self.db.cursor.fetchone() is not None

    def get_role_mention(self, role_name):
        role_id = self.role_ids.get(role_name)
        if role_id:
            return f"<@&{role_id}>"
        return f"@{role_name}"

bot = MiddlemanBot()

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user.name} (ID: {bot.user.id})")
    print(f"📊 Connected to {len(bot.guilds)} servers:")
    for guild in bot.guilds:
        print(f"  - {guild.name} (ID: {guild.id})")
    print("✅ Bot is ready to use!")
    try:
        await bot.tree.sync()
        print("✅ Slash commands synced successfully!")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

@bot.event
async def on_member_join(member):
    role = member.guild.get_role(bot.role_ids['Auto Role Member'])
    if role:
        try:
            await member.add_roles(role)
            print(f"✅ Added Auto Role Member to {member.name}")
        except:
            pass
    welcome_channel = bot.get_channel(bot.welcome_channel)
    if welcome_channel:
        embed = discord.Embed(title="Buy Robux™ | New Member Joined", color=discord.Color.blue())
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="User ID", value=member.id, inline=True)
        embed.add_field(name="Invited By", value="Unknown", inline=True)
        embed.add_field(name="Invite Code", value="Unknown", inline=True)
        embed.add_field(name="Account Created", value=member.created_at.strftime("%A, %B %d, %Y %I:%M %p"), inline=False)
        embed.set_footer(text="Buy Robux™ | Invite Tracker")
        try:
            await welcome_channel.send(embed=embed)
        except:
            pass

@bot.command(name='warn')
async def warn_command(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    if not bot.has_permission(ctx.author, ['Moderator', 'Coordinator', 'Overseer', 'Head of Management', 'Head of Coordination', 'Head of Operations', 'Head of Staff', 'President']):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    bot.db.add_warning(member.id, ctx.author.id, reason)
    warnings = bot.db.get_warnings(member.id)
    embed = discord.Embed(title="⚠️ User Warned", color=discord.Color.orange(), timestamp=datetime.now())
    embed.add_field(name="User", value=member.mention, inline=True)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Total Warnings", value=len(warnings), inline=True)
    await ctx.send(embed=embed)

@bot.command(name='clearwarn')
async def clearwarn_command(ctx, member: discord.Member):
    if not bot.has_permission(ctx.author, ['Moderator', 'Coordinator', 'Overseer', 'Head of Management', 'Head of Coordination', 'Head of Operations', 'Head of Staff', 'President']):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    bot.db.clear_warnings(member.id)
    embed = discord.Embed(title="✅ Warnings Cleared", description=f"All warnings for {member.mention} have been cleared.", color=discord.Color.green())
    await ctx.send(embed=embed)

@bot.command(name='delwarn')
async def delwarn_command(ctx, warning_id: int):
    if not bot.has_permission(ctx.author, ['Moderator', 'Coordinator', 'Overseer', 'Head of Management', 'Head of Coordination', 'Head of Operations', 'Head of Staff', 'President']):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    bot.db.delete_warning(warning_id)
    await ctx.send(f"✅ Warning {warning_id} deleted!")

@bot.command(name='info')
async def info_command(ctx):
    embed = discord.Embed(title="📋 ROLE REQUIREMENTS", description="Levi's Middleman Services", color=discord.Color.blue())
    requirements = ""
    role_list = list(bot.role_requirements.keys())
    for i, role in enumerate(role_list):
        req = bot.role_requirements[role]
        role_ping = bot.get_role_mention(role)
        if 'hits' in req:
            if 'discount' in req:
                prev_role_ping = bot.get_role_mention(role_list[i-1]) if i > 0 else ""
                requirements += f"**{role_ping}**\n   • {req['hits']} hits OR ${req['price']} | ${req['discount']} if already {prev_role_ping}\n\n"
            else:
                requirements += f"**{role_ping}**\n   • {req['hits']} hits OR ${req['price']}\n\n"
        else:
            if 'discount' in req:
                prev_role_ping = bot.get_role_mention(role_list[i-1]) if i > 0 else ""
                requirements += f"**{role_ping}**\n   • ${req['price']} | ${req['discount']} if already {prev_role_ping}\n\n"
            else:
                requirements += f"**{role_ping}**\n   • ${req['price']}\n\n"
    embed.description = requirements
    await ctx.send(embed=embed)

@bot.command(name='perks')
async def perks_command(ctx):
    gp_ping = bot.get_role_mention('Giveaway Pings')
    tm_ping = bot.get_role_mention('Trial Middleman')
    m_ping = bot.get_role_mention('Middleman')
    lm_ping = bot.get_role_mention('Lead Middleman')
    mod_ping = bot.get_role_mention('Moderator')
    coord_ping = bot.get_role_mention('Coordinator')
    ovr_ping = bot.get_role_mention('Overseer')
    hom_ping = bot.get_role_mention('Head of Management')
    hoc_ping = bot.get_role_mention('Head of Coordination')
    hoop_ping = bot.get_role_mention('Head of Operations')
    hodev_ping = bot.get_role_mention('Head of Dev')
    hos_ping = bot.get_role_mention('Head of Staff')
    pres_ping = bot.get_role_mention('President')
    perks_text = f"""⭐ ROLE PERKS - Levi's Middleman Services

**{gp_ping}** — Get this role after accepting the Mercy Program, hitters only.

**{tm_ping}** — Claim tickets, handle tickets, use middleman commands, view transcripts.

**{m_ping}** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members.

**{lm_ping}** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members.

**{mod_ping}** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members.

**{coord_ping}** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members.

**{ovr_ping}** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members, ban members, unban members, sell Trial Middleman, promote Trial Middleman.

**{hom_ping}** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members, ban members, unban members, sell and promote Overseer and below.

**{hoc_ping}** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members, ban members, unban members, sell and promote Head of Management and below.

**{hoop_ping}** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members, ban members, unban members, sell and promote Head of Coordination and below.

**{hodev_ping}** — Develop bots, develop systems, configure bots, manage integrations.

**{hos_ping}** — Claim tickets, handle tickets, use middleman commands, view transcripts, warn members, mute members, unmute members, timeout members, ban members, unban members, sell and promote Head of Operations and below.

**{pres_ping}** — Admin perms, can do all perms below, and sell all roles below."""
    chunks = [perks_text[i:i+1900] for i in range(0, len(perks_text), 1900)]
    for chunk in chunks:
        await ctx.send(chunk)

def build_middleman_panel_embed():
    embed = discord.Embed(title="Levi's Middleman Services | MM Service", color=discord.Color.from_rgb(47, 49, 54))
    embed.description = "Welcome to our middleman service centre.\n\nAt Levi's Middleman Services, we value and provide a safe and secure way to exchange your goods.\n\nIf you've found a trade and want to ensure your safety, you can use our middleman service.\n\u2014\n**Usage Conditions:**\n\u2022 Both parties agree to trade before requesting a middleman.\n\u2022 State the trade and value.\n\u2022 Fake or troll tickets will result in punishments.\n\n*Powered by Levi's Middleman Services*"
    embed.set_footer(text="Levi's Middleman Services")
    return embed

def build_support_panel_embed():
    embed = discord.Embed(title="Levi's Middleman Services | Support Centre", color=discord.Color.from_rgb(47, 49, 54))
    embed.description = "Welcome to our support centre.\n\nThis panel is for account, server, or general issues that are **not** related to an active trade. If you need a trade handled, use the middleman panel instead.\n\u2014\n**Before You Open a Ticket:**\n\u2022 Check `/faq` \u2014 your question may already be answered.\n\u2022 Have any relevant details ready, such as screenshots or order information.\n\u2022 Only one open support ticket per person at a time.\n\n*Powered by Levi's Middleman Services*"
    embed.set_footer(text="Levi's Middleman Services")
    return embed

# ==================== VIEWS ====================

async def _create_ticket_channel(bot, interaction, category_id, allowed_role_names, ticket_type, name_prefix):
    guild = interaction.guild
    category = discord.utils.get(guild.categories, id=category_id)
    if not category:
        await interaction.response.send_message("This ticket category isn't configured yet.", ephemeral=True)
        return None
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    for role_name in allowed_role_names:
        role_id = bot.role_ids.get(role_name)
        role = guild.get_role(role_id) if role_id else None
        if role:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    try:
        channel = await guild.create_text_channel(f"{name_prefix}-{interaction.user.name}", category=category, overwrites=overwrites)
    except:
        await interaction.response.send_message("Failed to create ticket channel.", ephemeral=True)
        return None
    bot.db.create_ticket(channel.id, interaction.user.id, ticket_type)
    return channel

class TicketPanelView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Request Middleman", style=discord.ButtonStyle.primary, emoji="🛡️", custom_id="middleman_request")
    async def request_middleman(self, interaction: discord.Interaction, button: discord.ui.Button):
        existing = self.bot.db.get_open_ticket(interaction.user.id, 'middleman')
        if existing:
            await interaction.response.send_message(f"You already have an open middleman ticket: <#{existing[0]}>", ephemeral=True)
            return
        await interaction.response.send_modal(MiddlemanRequestModal(self.bot))

class MiddlemanRequestModal(discord.ui.Modal, title="Request a Middleman"):
    other_person = discord.ui.TextInput(label="Who is the other person?", placeholder="Enter their Discord username and ID", style=discord.TextStyle.short, max_length=100)
    trade_details = discord.ui.TextInput(label="What is the trade?", placeholder="Describe the items/game/currency being traded", style=discord.TextStyle.paragraph, max_length=500)
    both_agreed = discord.ui.TextInput(label="Did both agree to this trade?", placeholder="Yes/No with proof if possible", style=discord.TextStyle.short, max_length=100)
    private_server = discord.ui.TextInput(label="Can you join a private server?", placeholder="Yes/No (link will be provided)", style=discord.TextStyle.short, max_length=100)

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        channel = await _create_ticket_channel(self.bot, interaction, self.bot.support_category, self.bot.middleman_staff_roles, 'middleman', 'mm')
        if not channel:
            return
        embed = discord.Embed(title="Middleman Ticket", description=f"Requested by {interaction.user.mention}. A middleman will claim this ticket shortly.", color=discord.Color.green())
        embed.add_field(name="Other Trader", value=str(self.other_person), inline=False)
        embed.add_field(name="Trade Details", value=str(self.trade_details), inline=False)
        embed.add_field(name="Both Parties Agreed", value=str(self.both_agreed), inline=True)
        embed.add_field(name="Private Server Available", value=str(self.private_server), inline=True)
        embed.set_footer(text="Levi's Middleman Services | Ticket opened")
        control_view = TicketControlView(self.bot)
        await channel.send(content=interaction.user.mention, embed=embed, view=control_view)
        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)

class SupportPanelView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Open Support Ticket", style=discord.ButtonStyle.secondary, emoji="🛠️", custom_id="support_request")
    async def open_support_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        existing = self.bot.db.get_open_ticket(interaction.user.id, 'support')
        if existing:
            await interaction.response.send_message(f"You already have an open support ticket: <#{existing[0]}>", ephemeral=True)
            return
        await interaction.response.send_modal(SupportRequestModal(self.bot))

class SupportRequestModal(discord.ui.Modal, title="Open a Support Ticket"):
    issue_summary = discord.ui.TextInput(label="What do you need help with?", placeholder="e.g. account issue, missing role, bug report", style=discord.TextStyle.short, max_length=100)
    issue_details = discord.ui.TextInput(label="Describe your issue", placeholder="Give as much detail as possible", style=discord.TextStyle.paragraph, max_length=1000)
    tried_already = discord.ui.TextInput(label="Have you already contacted staff?", placeholder="Yes/No — who, if applicable", style=discord.TextStyle.short, max_length=100, required=False)

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        channel = await _create_ticket_channel(self.bot, interaction, self.bot.general_support_category, self.bot.support_staff_roles, 'support', 'support')
        if not channel:
            return
        embed = discord.Embed(title="Support Ticket", description=f"Opened by {interaction.user.mention}. A staff member will assist you shortly.", color=discord.Color.blue())
        embed.add_field(name="Issue", value=str(self.issue_summary), inline=False)
        embed.add_field(name="Details", value=str(self.issue_details), inline=False)
        if str(self.tried_already):
            embed.add_field(name="Already Contacted Staff", value=str(self.tried_already), inline=False)
        embed.set_footer(text="Levi's Middleman Services | Support ticket opened")
        control_view = TicketControlView(self.bot)
        await channel.send(content=interaction.user.mention, embed=embed, view=control_view)
        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.primary, emoji="🙋", custom_id="middleman_claim_ticket")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.bot.is_ticket_channel(interaction.channel):
            await interaction.response.send_message("This is not an open ticket channel.", ephemeral=True)
            return
        if not self.bot.has_middleman_permission(interaction.user):
            await interaction.response.send_message("You need a staff role to claim tickets.", ephemeral=True)
            return
        ticket = self.bot.db.get_ticket(interaction.channel.id)
        if ticket and ticket[1]:
            claimer = interaction.guild.get_member(ticket[1])
            claimer_mention = claimer.mention if claimer else f"<@{ticket[1]}>"
            await interaction.response.send_message(f"This ticket is already claimed by {claimer_mention}.", ephemeral=True)
            return
        self.bot.db.claim_ticket(interaction.channel.id, interaction.user.id)
        button.disabled = True
        button.label = f"Claimed by {interaction.user.display_name}"
        await interaction.response.edit_message(view=self)
        await interaction.channel.send(f"{interaction.user.mention} has claimed this ticket and will assist you shortly.")

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="middleman_close_ticket")
    async def close_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.bot.is_ticket_channel(interaction.channel):
            await interaction.response.send_message("This is not an open ticket channel.", ephemeral=True)
            return
        if not self.bot.has_middleman_permission(interaction.user):
            await interaction.response.send_message("You don't have permission to close this ticket.", ephemeral=True)
            return
        self.bot.db.cursor.execute("UPDATE tickets SET status = 'closed', closed_at = ? WHERE channel_id = ?", (datetime.now(), interaction.channel.id))
        self.bot.db.conn.commit()
        await interaction.response.send_message("This ticket will be closed in 5 seconds...")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except:
            pass

class MercyView(discord.ui.View):
    def __init__(self, bot, target_user_id):
        super().__init__(timeout=60)
        self.bot = bot
        self.target_user_id = target_user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target_user_id:
            await interaction.response.send_message("❌ This offer isn't for you!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success, custom_id="mercy_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.bot.db.add_mercy_user(interaction.user.id)
        role = interaction.guild.get_role(self.bot.role_ids['Giveaway Pings'])
        if role:
            try:
                await interaction.user.add_roles(role)
            except:
                pass
        for item in self.children:
            item.disabled = True
        embed = discord.Embed(title="✅ Mercy Accepted", description=f"{interaction.user.mention} has accepted the Mercy Program offer and received the Giveaway Pings role.", color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=self)
        followup_embed = discord.Embed(title="🚀 Ready to get started?", description="You're in! Whenever you're ready, we can walk you through your first steps in the program.\n\nHit the button below to get going.", color=discord.Color.purple())
        followup_embed.set_footer(text="Levi's Middleman Services | Mercy System")
        await interaction.followup.send(embed=followup_embed, view=GetStartedView(self.bot), ephemeral=True)

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger, custom_id="mercy_decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        embed = discord.Embed(title="❌ Mercy Declined", description=f"{interaction.user.mention} has declined the Mercy Program offer.", color=discord.Color.red())
        await interaction.response.edit_message(embed=embed, view=self)

class GetStartedView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.button(label="🚀 Let's go!", style=discord.ButtonStyle.success, custom_id="mercy_get_started")
    async def get_started(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        embed = discord.Embed(title="📋 Getting Started", description="**STEP 1:**\nFind trades inside other servers, dont tend to overpay too much to make it sound legit. Once you find a trade, make sure its confirmed.\n\n**STEP 2:**\nClick the Request Middleman button to keep the trade running WITH the middleman, after the middleman gets the stuff you will split the profits 50/50.\n\n**How do I make profit?**\nYou make profit by these 2 things:\n• Splitting with the middleman\n• Getting middleman role at 5 hits\n\nOnce you have middleman you can Middleman peoples hits.", color=discord.Color.purple())
        embed.set_footer(text="Levi's Middleman Services | Mercy System")
        await interaction.response.edit_message(embed=embed, view=self)

# ==================== RUN BOT ====================

if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("❌ DISCORD_TOKEN environment variable not set!")
    else:
        bot.run(token)
