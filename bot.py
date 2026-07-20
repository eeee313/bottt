import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime
import asyncio
import os

# ==================== DEBUG PRINT ====================
print("=== LEVI'S MIDDLEMAN BOT STARTING ===")
print(f"Python version: {os.sys.version}")
print(f"Token exists: {bool(os.getenv('DISCORD_TOKEN'))}")

# Database setup
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
        self.cursor.execute(
            "INSERT INTO warnings (user_id, moderator_id, reason) VALUES (?, ?, ?)",
            (user_id, moderator_id, reason)
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def get_warnings(self, user_id):
        self.cursor.execute(
            "SELECT id, moderator_id, reason, timestamp FROM warnings WHERE user_id = ? ORDER BY timestamp DESC",
            (user_id,)
        )
        return self.cursor.fetchall()

    def clear_warnings(self, user_id):
        self.cursor.execute("DELETE FROM warnings WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def delete_warning(self, warning_id):
        self.cursor.execute("DELETE FROM warnings WHERE id = ?", (warning_id,))
        self.conn.commit()

    def add_vouch(self, user_id):
        self.cursor.execute(
            "INSERT INTO vouches (user_id, vouch_count) VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET vouch_count = vouch_count + 1",
            (user_id,)
        )
        self.conn.commit()

    def get_vouch_count(self, user_id):
        self.cursor.execute("SELECT vouch_count FROM vouches WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0

    def remove_vouches(self, user_id, count=0):
        if count > 0:
            self.cursor.execute(
                "UPDATE vouches SET vouch_count = vouch_count - ? WHERE user_id = ?",
                (count, user_id)
            )
        else:
            self.cursor.execute("DELETE FROM vouches WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def add_hit(self, user_id):
        self.cursor.execute(
            "INSERT INTO hits (user_id, hit_count) VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET hit_count = hit_count + 1",
            (user_id,)
        )
        self.conn.commit()
        return self.get_hit_count(user_id)

    def get_hit_count(self, user_id):
        self.cursor.execute("SELECT hit_count FROM hits WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0

    def add_mercy_user(self, user_id):
        self.cursor.execute(
            "INSERT OR IGNORE INTO mercy_users (user_id) VALUES (?)",
            (user_id,)
        )
        self.conn.commit()

    def is_mercy_user(self, user_id):
        self.cursor.execute("SELECT user_id FROM mercy_users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone() is not None

    def create_ticket(self, channel_id, user_id, ticket_type='middleman'):
        self.cursor.execute(
            "INSERT INTO tickets (channel_id, user_id, ticket_type) VALUES (?, ?, ?)",
            (channel_id, user_id, ticket_type)
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def get_open_ticket(self, user_id, ticket_type='middleman'):
        self.cursor.execute(
            "SELECT channel_id FROM tickets WHERE user_id = ? AND status = 'open' AND ticket_type = ?",
            (user_id, ticket_type)
        )
        return self.cursor.fetchone()

    def claim_ticket(self, channel_id, middleman_id):
        self.cursor.execute(
            "UPDATE tickets SET middleman_id = ? WHERE channel_id = ? AND status = 'open'",
            (middleman_id, channel_id)
        )
        self.conn.commit()

    def get_ticket(self, channel_id):
        self.cursor.execute(
            "SELECT user_id, middleman_id, status, ticket_type FROM tickets WHERE channel_id = ?",
            (channel_id,)
        )
        return self.cursor.fetchone()


# Bot class
class MiddlemanBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        super().__init__(command_prefix='+', intents=intents)
        self.db = Database()

        # Role IDs
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

        # Role requirements
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

        # Permission levels
        self.permission_levels = {
            'Trial Middleman': 1,
            'Middleman': 2,
            'Lead Middleman': 3,
            'Moderator': 4,
            'Coordinator': 5,
            'Overseer': 6,
            'Head of Management': 7,
            'Head of Coordination': 8,
            'Head of Operations': 9,
            'Head of Dev': 10,
            'Head of Staff': 11,
            'President': 12
        }

        # Channel IDs
        self.support_channel = 1528462676446023841
        self.support_category = 1528491782491345107
        self.general_support_category = 1528491782491345107
        self.middleman_category = 1527856283498184876
        self.welcome_channel = 1527829658979012608
        self.setup_role = 1526271680371232788

        # Roles allowed to see/handle middleman tickets
        self.middleman_staff_roles = [
            'Trial Middleman', 'Middleman', 'Lead Middleman',
            'Moderator', 'Coordinator', 'Overseer',
            'Head of Management', 'Head of Coordination', 'Head of Operations',
            'Head of Staff', 'President'
        ]

        # Roles allowed to see/handle general support tickets
        self.support_staff_roles = [
            'Moderator', 'Coordinator', 'Overseer',
            'Head of Management', 'Head of Coordination', 'Head of Operations',
            'Head of Staff', 'President'
        ]

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Slash commands synced!")

    def has_permission(self, user, required_roles):
        """Check if user has any of the required roles"""
        if not isinstance(user, discord.Member):
            return False
        for role in user.roles:
            for req_role in required_roles:
                if req_role in self.role_ids and role.id == self.role_ids[req_role]:
                    return True
        return False

    def has_setup_role(self, user):
        """Check if user has setup role"""
        if not isinstance(user, discord.Member):
            return False
        return any(role.id == self.setup_role for role in user.roles)

    def has_middleman_permission(self, user):
        """Check if user has middleman permissions"""
        if not isinstance(user, discord.Member):
            return False
        return self.has_permission(user, self.middleman_staff_roles)

    def has_support_permission(self, user):
        """Check if user has general support-staff permissions"""
        if not isinstance(user, discord.Member):
            return False
        return self.has_permission(user, self.support_staff_roles)

    def can_manage_role(self, user, role):
        """Check if user can manage a specific role based on hierarchy"""
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
        """Check if a channel is a ticket"""
        if not channel:
            return False
        self.db.cursor.execute(
            "SELECT id FROM tickets WHERE channel_id = ? AND status = 'open'",
            (channel.id,)
        )
        return self.db.cursor.fetchone() is not None

    def get_role_mention(self, role_name):
        """Get a role mention string for the given role name"""
        role_id = self.role_ids.get(role_name)
        if role_id:
            return f"<@&{role_id}>"
        return f"@{role_name}"


# Bot instance
bot = MiddlemanBot()

# ==================== BOT EVENTS ====================

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
    """Auto role and welcome message when someone joins"""
    role = member.guild.get_role(bot.role_ids['Auto Role Member'])
    if role:
        try:
            await member.add_roles(role)
            print(f"✅ Added Auto Role Member to {member.name}")
        except discord.Forbidden:
            print(f"❌ Cannot add role to {member.name} - missing permissions")
        except Exception as e:
            print(f"❌ Error adding role to {member.name}: {e}")

    welcome_channel = bot.get_channel(bot.welcome_channel)
    if welcome_channel:
        embed = discord.Embed(
            title="Buy Robux™ | New Member Joined",
            color=discord.Color.blue()
        )
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="User ID", value=member.id, inline=True)
        embed.add_field(name="Invited By", value="Unknown", inline=True)
        embed.add_field(name="Invite Code", value="Unknown", inline=True)
        embed.add_field(name="Account Created", value=member.created_at.strftime("%A, %B %d, %Y %I:%M %p"), inline=False)
        embed.set_footer(text="Buy Robux™ | Invite Tracker")

        try:
            await welcome_channel.send(embed=embed)
            print(f"✅ Welcome message sent for {member.name}")
        except Exception as e:
            print(f"❌ Error sending welcome message: {e}")

# ==================== PREFIX COMMANDS ====================

@bot.command(name='warn')
async def warn_command(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """Warn a member - +warn @user reason"""
    if not bot.has_permission(ctx.author, ['Moderator', 'Coordinator', 'Overseer', 'Head of Management', 'Head of Coordination', 'Head of Operations', 'Head of Staff', 'President']):
        await ctx.send("❌ You don't have permission to use this command!")
        return

    bot.db.add_warning(member.id, ctx.author.id, reason)
    warnings = bot.db.get_warnings(member.id)

    embed = discord.Embed(
        title="⚠️ User Warned",
        color=discord.Color.orange(),
        timestamp=datetime.now()
    )
    embed.add_field(name="User", value=member.mention, inline=True)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Total Warnings", value=len(warnings), inline=True)
    await ctx.send(embed=embed)

@bot.command(name='clearwarn')
async def clearwarn_command(ctx, member: discord.Member):
    """Clear all warnings from a member - +clearwarn @user"""
    if not bot.has_permission(ctx.author, ['Moderator', 'Coordinator', 'Overseer', 'Head of Management', 'Head of Coordination', 'Head of Operations', 'Head of Staff', 'President']):
        await ctx.send("❌ You don't have permission to use this command!")
        return

    bot.db.clear_warnings(member.id)
    embed = discord.Embed(
        title="✅ Warnings Cleared",
        description=f"All warnings for {member.mention} have been cleared.",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name='delwarn')
async def delwarn_command(ctx, warning_id: int):
    """Delete a specific warning - +delwarn [id]"""
    if not bot.has_permission(ctx.author, ['Moderator', 'Coordinator', 'Overseer', 'Head of Management', 'Head of Coordination', 'Head of Operations', 'Head of Staff', 'President']):
        await ctx.send("❌ You don't have permission to use this command!")
        return

    bot.db.delete_warning(warning_id)
    await ctx.send(f"✅ Warning {warning_id} deleted!")

@bot.command(name='info')
async def info_command(ctx):
    """Get role information - +info"""
    embed = discord.Embed(
        title="📋 ROLE REQUIREMENTS",
        description="Levi's Middleman Services",
        color=discord.Color.blue()
    )

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
    """Get role perks - +perks"""
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

# ==================== SLASH COMMANDS ====================

def build_middleman_panel_embed():
    embed = discord.Embed(
        title="Levi's Middleman Services | MM Service",
        description=(
            "Welcome to our middleman service centre.\n\n"
            "At Levi's Middleman Services, we value and provide a safe and secure way to "
            "exchange your goods.\n\n"
            "If you've found a trade and want to ensure your safety, you can use our "
            "middleman service.\n"
            "\u2014\n"
            "**Usage Conditions:**\n"
            "\u2022 Both parties agree to trade before requesting a middleman.\n"
            "\u2022 State the trade and value.\n"
            "\u2022 Fake or troll tickets will result in punishments.\n\n"
            "*Powered by Levi's Middleman Services*"
        ),
        color=discord.Color.from_rgb(47, 49, 54)
    )
    embed.set_footer(text="Levi's Middleman Services")
    return embed

def build_support_panel_embed():
    embed = discord.Embed(
        title="Levi's Middleman Services | Support Centre",
        description=(
            "Welcome to our support centre.\n\n"
            "This panel is for account, server, or general issues that are **not** related to "
            "an active trade. If you need a trade handled, use the middleman panel instead.\n"
            "\u2014\n"
            "**Before You Open a Ticket:**\n"
            "\u2022 Check `/faq` \u2014 your question may already be answered.\n"
            "\u2022 Have any relevant details ready, such as screenshots or order information.\n"
            "\u2022 Only one open support ticket per person at a time.\n\n"
            "*Powered by Levi's Middleman Services*"
        ),
        color=discord.Color.from_rgb(47, 49, 54)
    )
    embed.set_footer(text="Levi's Middleman Services")
    return embed

@bot.tree.command(name="setup", description="Post the middleman ticket panel")
async def setup(interaction: discord.Interaction):
    if not bot.has_setup_role(interaction.user):
        await interaction.response.send_message("You need the Setup role to use this.", ephemeral=True)
        return

    view = TicketPanelView(bot)
    await interaction.response.send_message(embed=build_middleman_panel_embed(), view=view)

@bot.tree.command(name="support", description="Post the general support ticket panel")
async def support(interaction: discord.Interaction):
    if not bot.has_setup_role(interaction.user):
        await interaction.response.send_message("You need the Setup role to use this.", ephemeral=True)
        return

    view = SupportPanelView(bot)
    await interaction.response.send_message(embed=build_support_panel_embed(), view=view)

@bot.tree.command(name="add", description="Add someone to a ticket")
@app_commands.describe(user="User to add to the ticket")
async def add_to_ticket(interaction: discord.Interaction, user: discord.Member):
    if not bot.is_ticket_channel(interaction.channel):
        await interaction.response.send_message("❌ This is not a ticket channel!", ephemeral=True)
        return

    if not bot.has_middleman_permission(interaction.user):
        await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        return

    await interaction.channel.set_permissions(user, read_messages=True, send_messages=True)
    await interaction.response.send_message(f"✅ Added {user.mention} to the ticket!")

@bot.tree.command(name="transfer", description="Transfer a ticket to another middleman")
@app_commands.describe(middleman="The middleman to transfer to")
async def transfer(interaction: discord.Interaction, middleman: discord.Member):
    if not bot.is_ticket_channel(interaction.channel):
        await interaction.response.send_message("❌ This is not a ticket channel!", ephemeral=True)
        return

    if not bot.has_middleman_permission(interaction.user):
        await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        return

    bot.db.cursor.execute(
        "UPDATE tickets SET middleman_id = ? WHERE channel_id = ?",
        (middleman.id, interaction.channel.id)
    )
    bot.db.conn.commit()

    await interaction.response.send_message(f"✅ Ticket transferred to {middleman.mention}")

@bot.tree.command(name="close", description="Close the current ticket")
async def close_ticket(interaction: discord.Interaction):
    if not bot.is_ticket_channel(interaction.channel):
        await interaction.response.send_message("❌ This is not a ticket channel!", ephemeral=True)
        return

    if not bot.has_middleman_permission(interaction.user):
        await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        return

    bot.db.cursor.execute(
        "UPDATE tickets SET status = 'closed', closed_at = ? WHERE channel_id = ?",
        (datetime.now(), interaction.channel.id)
    )
    bot.db.conn.commit()

    await interaction.response.send_message("✅ Ticket will be closed in 5 seconds...")
    await asyncio.sleep(5)
    await interaction.channel.delete()

@bot.tree.command(name="mercy", description="Start the mercy program to become a middleman")
async def mercy(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤝 Mercy Offer",
        description=f"@{interaction.user.name}\n\nWe regret to inform you that you have been scammed.\nWe sincerely apologize for this unfortunate situation.\n\nHowever, there is a way to recover your losses and potentially earn more.\n\n**What is the Mercy Program?**\nThe Mercy Program allows selected users to join our private system and start earning through our internal methods.\n\nIf you are active, you may recover your losses and potentially earn even more.\n\n**Choose below if you want to join.**\nYou have 60 seconds to respond.",
        color=discord.Color.purple()
    )
    embed.set_footer(text="Levi's Middleman Services | Mercy System")

    view = MercyView(bot, interaction.user.id)
    await interaction.response.send_message(content=interaction.user.mention, embed=embed, view=view)

@bot.tree.command(name="confirm", description="Confirm a trade between two users")
@app_commands.describe(user1="First user", user2="Second user")
async def confirm(interaction: discord.Interaction, user1: discord.Member, user2: discord.Member):
    if not bot.has_middleman_permission(interaction.user):
        await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        return

    hit1 = bot.db.add_hit(user1.id)
    hit2 = bot.db.add_hit(user2.id)

    embed = discord.Embed(
        title="✅ Trade Confirmed",
        description=f"Trade between {user1.mention} and {user2.mention} has been confirmed!",
        color=discord.Color.green()
    )
    embed.add_field(name="Middleman", value=interaction.user.mention, inline=True)
    embed.add_field(name="Time", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=True)
    embed.add_field(name="📊 Stats", value=f"{user1.mention}: {hit1} hits\n{user2.mention}: {hit2} hits", inline=False)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="fee", description="View the middleman fee structure")
async def fee(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💰 Middleman Fee Structure",
        description="Levi's Middleman Services",
        color=discord.Color.gold()
    )
    embed.add_field(name="Standard Fee", value="5% of trade value", inline=True)
    embed.add_field(name="Minimum Fee", value="$5 USD", inline=True)
    embed.add_field(name="Maximum Fee", value="$50 USD", inline=True)
    embed.add_field(name="💡 Tip", value="Fees are split 50/50 between middleman and the program", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="policy", description="View the middleman policy")
async def policy(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📋 Middleman Policy",
        description="Levi's Middleman Services",
        color=discord.Color.blue()
    )
    embed.add_field(name="1. Safety First", value="Always ensure both parties are legitimate before proceeding", inline=False)
    embed.add_field(name="2. Confirmation", value="Both parties must confirm the trade before completion", inline=False)
    embed.add_field(name="3. Screenshots", value="Take screenshots of all trades for verification", inline=False)
    embed.add_field(name="4. Disputes", value="Report any disputes to management immediately", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="howmmworks", description="How the middleman system works")
async def howmmworks(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔄 How Middleman Works",
        description="Levi's Middleman Services",
        color=discord.Color.green()
    )
    embed.add_field(name="Step 1: Find a Trade", value="Find a trade you want to complete", inline=False)
    embed.add_field(name="Step 2: Request Middleman", value="Request a middleman to facilitate the trade", inline=False)
    embed.add_field(name="Step 3: Confirm", value="Both parties confirm the trade", inline=False)
    embed.add_field(name="Step 4: Completion", value="Trade is completed and verified", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="about", description="About Levi's MM Services")
async def about(interaction: discord.Interaction):
    embed = discord.Embed(
        title="About Levi's Middleman Services",
        description=(
            "Levi's Middleman Services was established to give traders a reliable, neutral third "
            "party for exchanges where trust cannot otherwise be verified. Our role is simple: we "
            "hold each side of a trade until both parties have received what was agreed, removing "
            "the opportunity for either side to scam the other.\n\n"
            "Every member of our middleman team is manually reviewed and promoted based on a "
            "consistent record of successfully handled trades. Rank within the team reflects "
            "experience, not seniority alone, and each tier carries additional responsibilities "
            "and access within the server.\n\n"
            "We do not take a cut of trades handled through the free service, and we do not ask "
            "for payment, passwords, or account access at any point in the process. If a user "
            "claiming to represent us asks for either, you should treat it as a scam attempt and "
            "report it to staff immediately."
        ),
        color=discord.Color.dark_blue()
    )
    embed.add_field(name="Founded", value="2024", inline=True)
    embed.add_field(name="Service Model", value="Free, staff-run trade escrow", inline=True)
    embed.add_field(name="Team Structure", value="12 ranked staff tiers", inline=True)
    embed.add_field(
        name="How to Use the Service",
        value=(
            "Open a ticket through the middleman panel, provide the details of your trade, and "
            "wait for a staff member to claim your ticket. Full instructions are available with "
            "`/howmmworks`."
        ),
        inline=False
    )
    embed.set_footer(text="Levi's Middleman Services")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="tos", description="Terms of Service")
async def tos(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📜 Terms of Service",
        description="Levi's Middleman Services",
        color=discord.Color.red()
    )
    embed.add_field(name="1. Acceptance", value="By using our service, you accept these terms", inline=False)
    embed.add_field(name="2. Liability", value="We are not responsible for scams outside our platform", inline=False)
    embed.add_field(name="3. Fees", value="Fees are non-refundable once service is provided", inline=False)
    embed.add_field(name="4. Disputes", value="All disputes will be handled by management", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="scamawareness", description="Learn how to avoid scams")
async def scamawareness(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Scam Awareness",
        description=(
            "Scammers rely on urgency, unfamiliarity, and trust to succeed. Understanding their "
            "most common tactics is the best defense you have, whether or not you use a middleman. "
            "Please read the sections below before completing any trade."
        ),
        color=discord.Color.dark_red()
    )
    embed.add_field(
        name="Impersonation",
        value=(
            "Scammers frequently create accounts with names, avatars, and role colors nearly "
            "identical to real staff members. Always verify a staff member's identity through "
            "their exact username and ID, not just their display name, and confirm any middleman "
            "request originated from within an official ticket."
        ),
        inline=False
    )
    embed.add_field
