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
        self.cursor.execute('CREATE TABLE IF NOT EXISTS warnings (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, moderator_id INTEGER, reason TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
        self.cursor.execute('CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id INTEGER, user_id INTEGER, middleman_id INTEGER, status TEXT DEFAULT "open", ticket_type TEXT DEFAULT "middleman", created_at DATETIME DEFAULT CURRENT_TIMESTAMP, closed_at DATETIME)')
        try:
            self.cursor.execute("ALTER TABLE tickets ADD COLUMN ticket_type TEXT DEFAULT 'middleman'")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass
        self.cursor.execute('CREATE TABLE IF NOT EXISTS vouches (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, vouch_count INTEGER DEFAULT 0)')
        self.cursor.execute('CREATE TABLE IF NOT EXISTS hits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, hit_count INTEGER DEFAULT 0)')
        self.cursor.execute('CREATE TABLE IF NOT EXISTS mercy_users (user_id INTEGER PRIMARY KEY, accepted_at DATETIME DEFAULT CURRENT_TIMESTAMP)')
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
        self.middleman_category = 1527856283498184876  # Tickets go here
        self.welcome_channel = 1527829658979012608
        self.setup_role = 1526271680371232788
        self.middleman_staff_roles = ['Trial Middleman', 'Middleman', 'Lead Middleman', 'Moderator', 'Coordinator', 'Overseer', 'Head of Management', 'Head of Coordination', 'Head of Operations', 'Head of Staff', 'President']
        self.support_staff_roles = ['Moderator', 'Coordinator', 'Overseer', 'Head of Management', 'Head of Coordination', 'Head of Operations', 'Head of Staff', 'President']

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

# ==================== EVENTS ====================

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user.name} (ID: {bot.user.id})")
    print(f"📊 Connected to {len(bot.guilds)} servers:")
    for guild in bot.guilds:
        print(f"  - {guild.name} (ID: {guild.id})")
    try:
        await bot.tree.sync()
        print("✅ Slash commands synced successfully!")
        cmds = await bot.tree.fetch_commands()
        print(f"📋 Registered {len(cmds)} slash commands:")
        for cmd in cmds:
            print(f"  - /{cmd.name}")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")
    print("✅ Bot is ready to use!")

@bot.event
async def on_member_join(member):
    role = member.guild.get_role(bot.role_ids['Auto Role Member'])
    if role:
        try:
            await member.add_roles(role)
        except discord.HTTPException:
            pass
    welcome_channel = bot.get_channel(bot.welcome_channel)
    if welcome_channel:
        embed = discord.Embed(title="Levi MM Services | New Member Joined", color=discord.Color.blue())
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="User ID", value=member.id, inline=True)
        embed.add_field(name="Account Created", value=member.created_at.strftime("%A, %B %d, %Y %I:%M %p"), inline=False)
        embed.set_footer(text="Levi MM Services | Invite Tracker")
        try:
            await welcome_channel.send(embed=embed)
        except discord.HTTPException:
            pass

# ==================== SLASH COMMANDS ====================

@bot.tree.command(name="ping", description="Test if slash commands work")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong! Slash commands are working!")

@bot.tree.command(name="setup", description="Post the middleman ticket panel")
async def setup(interaction: discord.Interaction):
    if not bot.has_setup_role(interaction.user):
        await interaction.response.send_message("❌ You need the Setup role to use this.", ephemeral=True)
        return
    view = TicketPanelView(bot)
    embed = discord.Embed(
        title="🛡️ Levi's Middleman Services",
        description="**Welcome to our official Middleman Service Centre**\n\n"
                    "We provide a safe and secure way to exchange your goods with complete peace of mind.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**📋 How It Works:**\n"
                    "• Click the button below to request a middleman\n"
                    "• A staff member will be assigned to your trade\n"
                    "• Both parties confirm the trade details\n"
                    "• Trade is completed safely and securely\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**⚠️ Important:**\n"
                    "• Both parties must agree before requesting\n"
                    "• Fake or troll tickets will result in punishment\n"
                    "• Keep all communication in the ticket\n\n"
                    "*Powered by Levi's Middleman Services*",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1338592957753725044/1338592957753725044/levi_logo.png")
    embed.set_footer(text="Levi's Middleman Services © 2024")
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="support", description="Post the general support ticket panel")
async def support(interaction: discord.Interaction):
    if not bot.has_setup_role(interaction.user):
        await interaction.response.send_message("❌ You need the Setup role to use this.", ephemeral=True)
        return
    view = SupportPanelView(bot)
    embed = discord.Embed(
        title="🛠️ Levi's Support Centre",
        description="**Welcome to our Official Support Centre**\n\n"
                    "Need help with an account, server, or general issue?\n"
                    "We're here to assist you.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**📋 Before Opening a Ticket:**\n"
                    "• Check `/faq` — your question may already be answered\n"
                    "• Have relevant details ready (screenshots, order info)\n"
                    "• Only one open support ticket per person\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**🛠️ What We Can Help With:**\n"
                    "• Account issues\n"
                    "• Server problems\n"
                    "• General questions\n"
                    "• Bug reports\n\n"
                    "*Powered by Levi's Middleman Services*",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1338592957753725044/1338592957753725044/levi_logo.png")
    embed.set_footer(text="Levi's Middleman Services © 2024")
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="offer", description="Offer the mercy program to a user")
@app_commands.describe(user="The user to offer mercy to")
async def offer_mercy(interaction: discord.Interaction, user: discord.Member):
    # Only Trial Middleman and above can use this
    if not bot.has_middleman_permission(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🤝 Mercy Program Invitation",
        description=f"You have been invited to join the **Mercy Program**!\n\n"
                    f"**What is the Mercy Program?**\n"
                    f"The Mercy Program allows selected users to join our private system and start earning through our internal methods.\n\n"
                    f"**What do I get?**\n"
                    f"• Access to our private system\n"
                    f"• Opportunity to earn\n"
                    f"• Giveaway Pings role\n\n"
                    f"**Choose below if you want to join.**",
        color=discord.Color.purple()
    )
    embed.set_footer(text="Levi's Middleman Services | Mercy System")
    
    view = MercyView(bot, user.id)
    await interaction.response.send_message(content=user.mention, embed=embed, view=view)

@bot.tree.command(name="about", description="About Levi's MM Services")
async def about(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📖 About Levi's Middleman Services",
        description="**Your Trusted Trading Partner**\n\n"
                    "Levi's Middleman Services was established to give traders a reliable, "
                    "neutral third party for exchanges where trust cannot otherwise be verified.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**Our Mission**\n"
                    "We provide a safe and secure environment for traders to exchange "
                    "goods without the risk of being scammed.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**Why Choose Us?**\n"
                    "• Professional and experienced staff\n"
                    "• Fast and reliable service\n"
                    "• Secure and safe trades\n"
                    "• 24/7 support availability\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**Founded:** 2024\n"
                    "**Service Model:** Free, staff-run trade escrow\n"
                    "**Team Structure:** 12 ranked staff tiers",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Levi's Middleman Services © 2024")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="faq", description="Frequently Asked Questions")
async def faq(interaction: discord.Interaction):
    embed = discord.Embed(
        title="❓ Frequently Asked Questions",
        description="**Answers to the questions we're asked most often.**\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**How do I request a middleman?**\n"
                    "Open the middleman panel and click 'Request Middleman'.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**Is the middleman service free?**\n"
                    "Yes! There is no fee to use a middleman for a standard trade.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**How do I become a staff member?**\n"
                    "New staff members are brought in through the Mercy Program.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**What are the requirements for each rank?**\n"
                    "Requirements vary by rank. Use `/info` for the full breakdown.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**How long does a trade take?**\n"
                    "Most tickets are claimed within a few minutes during active hours.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**Can I open a ticket for something other than a trade?**\n"
                    "Yes! Use the support panel for account or server issues.",
        color=discord.Color.teal()
    )
    embed.set_footer(text="Levi's Middleman Services © 2024")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="tos", description="Terms of Service")
async def tos(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📜 Terms of Service",
        description="**Levi's Middleman Services - Terms of Service**\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**1. Acceptance of Terms**\n"
                    "By using our service, you agree to these terms and conditions.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**2. Service Liability**\n"
                    "We are not responsible for scams that occur outside our platform.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**3. Fees and Payments**\n"
                    "All fees are non-refundable once the service has been provided.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**4. Dispute Resolution**\n"
                    "All disputes will be handled fairly by management.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**5. User Conduct**\n"
                    "Users must behave respectfully and follow staff instructions.",
        color=discord.Color.red()
    )
    embed.set_footer(text="Levi's Middleman Services © 2024")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="scamawareness", description="Learn how to avoid scams")
async def scamawareness(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🚨 Scam Awareness Guide",
        description="**Protect Yourself from Scammers**\n\n"
                    "Scammers rely on urgency, unfamiliarity, and trust to succeed. "
                    "Read this guide to stay safe.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**⚠️ Impersonation**\n"
                    "Scammers create accounts with names and avatars nearly identical to real staff. "
                    "Always verify a staff member's identity through their exact username and ID.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**⚠️ Fake Trust or Middleman Sites**\n"
                    "Never conduct a trade through a third-party website or bot that is not "
                    "officially listed by our service.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**⚠️ Pressure and Urgency**\n"
                    "Scammers rush trades by claiming limited-time offers or that someone "
                    "else is buying it right now. Legitimate trades don't skip verification.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**⚠️ Requests for Sensitive Information**\n"
                    "No legitimate staff will ever ask for your password, 2FA codes, "
                    "payment card details, or remote access to your device.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**✅ Before You Trade**\n"
                    "• Confirm terms in writing\n"
                    "• Keep screenshots of all agreements\n"
                    "• Use the official ticket system\n\n"
                    "**If You Believe You Are Being Scammed:**\n"
                    "Stop the trade immediately and open a ticket to report the situation.",
        color=discord.Color.dark_red()
    )
    embed.set_footer(text="Levi's Middleman Services © 2024")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="howmmworks", description="How the middleman system works")
async def howmmworks(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔄 How Middleman Works",
        description="**Step-by-Step Guide**\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**Step 1: Find a Trade**\n"
                    "Find a trade you want to complete and confirm with the other party.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**Step 2: Request a Middleman**\n"
                    "Click 'Request Middleman' and provide the trade details.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**Step 3: Wait for a Staff Member**\n"
                    "A staff member will claim your ticket and assist you.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**Step 4: Confirm the Trade**\n"
                    "Both parties confirm the trade details with the middleman.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**Step 5: Trade Completion**\n"
                    "The trade is completed and verified by the middleman.",
        color=discord.Color.green()
    )
    embed.set_footer(text="Levi's Middleman Services © 2024")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="fee", description="View the middleman fee structure")
async def fee(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💰 Middleman Fee Structure",
        description="**Transparent Pricing**\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**Standard Fee**\n"
                    "5% of trade value\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**Minimum Fee**\n"
                    "$5 USD\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**Maximum Fee**\n"
                    "$50 USD\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**💡 Tip**\n"
                    "Fees are split 50/50 between the middleman and the program.",
        color=discord.Color.gold()
    )
    embed.set_footer(text="Levi's Middleman Services © 2024")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="policy", description="View the middleman policy")
async def policy(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📋 Middleman Policy",
        description="**Our Core Policies**\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**1. Safety First**\n"
                    "Always ensure both parties are legitimate before proceeding.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**2. Confirmation**\n"
                    "Both parties must confirm the trade before completion.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**3. Screenshots**\n"
                    "Take screenshots of all trades for verification.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "**4. Disputes**\n"
                    "Report any disputes to management immediately.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Levi's Middleman Services © 2024")
    await interaction.response.send_message(embed=embed)

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
    embed.add_field(name="📊 Stats", value=f"{user1.mention}: {hit1} hits\n{user2.mention}: {hit2} hits", inline=False)
    await interaction.response.send_message(embed=embed)

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
    bot.db.cursor.execute("UPDATE tickets SET middleman_id = ? WHERE channel_id = ?", (middleman.id, interaction.channel.id))
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
    bot.db.cursor.execute("UPDATE tickets SET status = 'closed', closed_at = ? WHERE channel_id = ?", (datetime.now(), interaction.channel.id))
    bot.db.conn.commit()
    await interaction.response.send_message("✅ Ticket will be closed in 5 seconds...")
    await asyncio.sleep(5)
    await interaction.channel.delete()

# ==================== PREFIX COMMANDS ====================

@bot.command(name='warn')
async def warn_command(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    if not bot.has_permission(ctx.author, ['Moderator', 'Coordinator', 'Overseer', 'Head of Management', 'Head of Coordination', 'Head of Operations', 'Head of Staff', 'President']):
        await ctx.send("❌ You don't have permission!")
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
        await ctx.send("❌ You don't have permission!")
        return
    bot.db.clear_warnings(member.id)
    embed = discord.Embed(title="✅ Warnings Cleared", description=f"All warnings for {member.mention} cleared.", color=discord.Color.green())
    await ctx.send(embed=embed)

@bot.command(name='delwarn')
async def delwarn_command(ctx, warning_id: int):
    if not bot.has_permission(ctx.author, ['Moderator', 'Coordinator', 'Overseer', 'Head of Management', 'Head of Coordination', 'Head of Operations', 'Head of Staff', 'President']):
        await ctx.send("❌ You don't have permission!")
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
    tm_ping = bot.get_role
