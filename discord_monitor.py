import discord
import re
import requests
import json
import os
from datetime import datetime, timedelta
from discord.ext import commands, tasks
from dotenv import load_dotenv
import pytz

load_dotenv()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Message deduplication tracking
processed_messages = set()
MAX_PROCESSED_CACHE = 1000  # Prevent memory buildup

# Environment variables
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
NOTION_DATABASE_ID = os.getenv('NOTION_DATABASE_ID')
CHANNEL_ID = int(os.getenv('CHANNEL_ID')) if os.getenv('CHANNEL_ID') else None
CISO_NAME = os.getenv('CISO_NAME', 'Your CISO')  # Your actual name
ADMIN_CODE = os.getenv('ADMIN_CODE')  # Secret admin authentication code

# Timezone setup
SAST = pytz.timezone('Africa/Johannesburg')

def get_sa_time():
    """Get current time in South African timezone"""
    return datetime.now(SAST)

def get_sa_date():
    """Get current date in South African timezone"""
    return get_sa_time().date()

# Notion API headers
NOTION_HEADERS = {
    'Authorization': f'Bearer {NOTION_TOKEN}',
    'Content-Type': 'application/json',
    'Notion-Version': '2022-06-28'
}

def parse_ciso_update(message_content, author):
    """Parse the structured CISO update message"""
    try:
        # Extract date
        date_pattern = r'Daily CISO Update - (.+?)(?:\n|$)'
        date_match = re.search(date_pattern, message_content, re.IGNORECASE)
        
        if date_match:
            date_str = date_match.group(1).strip()
            # Try to parse various date formats and convert to ISO format
            try:
                # Handle formats like "June 13, 2025", "06/13/2025", "2025-06-13"
                if ',' in date_str:  # "June 13, 2025" format
                    parsed_date = datetime.strptime(date_str, '%B %d, %Y')
                elif '/' in date_str:  # "06/13/2025" or "13/06/2025" format
                    try:
                        parsed_date = datetime.strptime(date_str, '%m/%d/%Y')
                    except:
                        parsed_date = datetime.strptime(date_str, '%d/%m/%Y')
                elif '-' in date_str:  # "2025-06-13" format (already correct)
                    parsed_date = datetime.strptime(date_str, '%Y-%m-%d')
                else:
                    # Fallback to current date
                    parsed_date = get_sa_time()
                
                # Convert to ISO format (YYYY-MM-DD)
                date_str = parsed_date.strftime('%Y-%m-%d')
                print(f"📅 Parsed date '{date_match.group(1).strip()}' -> '{date_str}'")
                
            except Exception as e:
                print(f"⚠️ Date parsing failed for '{date_str}': {e}")
                date_str = get_sa_date().strftime('%Y-%m-%d')
        else:
            date_str = get_sa_date().strftime('%Y-%m-%d')
        
        # Extract student name - prioritize from message, fallback to Discord display name
        student_pattern = r'Student:\s*(.+?)(?:\n|$)'
        student_match = re.search(student_pattern, message_content, re.IGNORECASE)
        student_name = student_match.group(1).strip() if student_match else (author.display_name or author.name)
        
        # Extract hours worked
        hours_pattern = r'Hours Worked:\s*(\d+)'
        hours_match = re.search(hours_pattern, message_content, re.IGNORECASE)
        hours_worked = int(hours_match.group(1)) if hours_match else 0
        
        # Extract completed today section
        completed_pattern = r'Completed Today:\s*(.*?)(?=Current Findings|Tomorrow\'s Plan|CISO Input|$)'
        completed_match = re.search(completed_pattern, message_content, re.DOTALL | re.IGNORECASE)
        completed_today = completed_match.group(1).strip() if completed_match else ""
        
        # Extract current findings/issues
        findings_pattern = r'Current Findings/Issues:\s*(.*?)(?=Tomorrow\'s Plan|CISO Input|$)'
        findings_match = re.search(findings_pattern, message_content, re.DOTALL | re.IGNORECASE)
        current_findings = findings_match.group(1).strip() if findings_match else ""
        
        # Extract tomorrow's plan
        tomorrow_pattern = r'Tomorrow\'s Plan:\s*(.*?)(?=CISO Input|$)'
        tomorrow_match = re.search(tomorrow_pattern, message_content, re.DOTALL | re.IGNORECASE)
        tomorrow_plan = tomorrow_match.group(1).strip() if tomorrow_match else ""
        
        # Extract CISO input needed
        ciso_pattern = r'CISO Input Needed:\s*(.*?)

def create_notion_entry(parsed_data):
    """Create a new entry in the Notion database"""
    try:
        # Parse date string to ISO format for Notion
        try:
            parsed_date = datetime.strptime(parsed_data['date'], '%Y-%m-%d')
            # Convert to SAST timezone
            parsed_date = SAST.localize(parsed_date)
        except:
            # Try different date formats
            try:
                parsed_date = datetime.strptime(parsed_data['date'], '%m/%d/%Y')
                parsed_date = SAST.localize(parsed_date)
            except:
                parsed_date = get_sa_time()
        
        # Notion database entry structure - UPDATED with Discord fields
        data = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": {
                "Date": {
                    "date": {"start": parsed_date.strftime('%Y-%m-%d')}
                },
                "Student Name": {
                    "title": [{"text": {"content": parsed_data['student_name']}}]
                },
                "Discord User ID": {
                    "rich_text": [{"text": {"content": parsed_data['discord_user_id']}}]
                },
                "Discord Username": {
                    "rich_text": [{"text": {"content": parsed_data['discord_username']}}]
                },
                "Discord Display Name": {
                    "rich_text": [{"text": {"content": parsed_data['discord_display_name']}}]
                },
                "Hours Worked": {
                    "number": parsed_data['hours_worked']
                },
                "Completed Today": {
                    "rich_text": [{"text": {"content": parsed_data['completed_today'][:2000]}}]  # Notion has character limits
                },
                "Current Findings": {
                    "rich_text": [{"text": {"content": parsed_data['current_findings'][:2000]}}]
                },
                "Tomorrow Plan": {
                    "rich_text": [{"text": {"content": parsed_data['tomorrow_plan'][:2000]}}]
                },
                "CISO Input Needed": {
                    "rich_text": [{"text": {"content": parsed_data['ciso_input'][:2000]}}]
                },
                "CISO Response": {
                    "rich_text": [{"text": {"content": ""}}]  # Empty field for CISO to fill
                },
                "Response Sent": {
                    "checkbox": False  # Track if response has been sent
                },
                "Status": {
                    "select": {"name": "New"}
                }
            }
        }
        
        # Send to Notion API
        response = requests.post(
            'https://api.notion.com/v1/pages',
            headers=NOTION_HEADERS,
            json=data
        )
        
        if response.status_code == 200:
            return True, "Entry created successfully"
        else:
            return False, f"Notion API error: {response.status_code} - {response.text}"
            
    except Exception as e:
        return False, f"Error creating Notion entry: {e}"

def get_entries_with_responses(target_date=None):
    """Fetch Notion entries that have CISO responses but haven't been sent yet"""
    try:
        if target_date is None:
            target_date = get_sa_date().strftime('%Y-%m-%d')
        
        # Query Notion database for entries with responses - ONLY for the specific date
        query_data = {
            "filter": {
                "and": [
                    {
                        "property": "Date",
                        "date": {
                            "equals": target_date  # STRICT date matching
                        }
                    },
                    {
                        "property": "CISO Response",
                        "rich_text": {
                            "is_not_empty": True
                        }
                    },
                    {
                        "property": "Response Sent",
                        "checkbox": {
                            "equals": False
                        }
                    }
                ]
            },
            "sorts": [
                {
                    "property": "Student Name",
                    "direction": "ascending"
                }
            ]
        }
        
        response = requests.post(
            f'https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query',
            headers=NOTION_HEADERS,
            json=query_data
        )
        
        if response.status_code == 200:
            results = response.json()['results']
            
            # ADDITIONAL SAFETY CHECK: Double-verify the date matches
            filtered_results = []
            for entry in results:
                entry_date = ""
                if 'Date' in entry['properties'] and entry['properties']['Date']['date']:
                    entry_date = entry['properties']['Date']['date']['start']
                
                # Convert target_date to match Notion's format for comparison
                try:
                    # Parse target_date (YYYY-MM-DD) and convert to Notion's format
                    target_dt = datetime.strptime(target_date, '%Y-%m-%d')
                    # Notion stores dates in YYYY-MM-DD format in the API
                    expected_notion_date = target_dt.strftime('%Y-%m-%d')
                    
                    # Only include if date exactly matches target date
                    if entry_date == expected_notion_date:
                        filtered_results.append(entry)
                        print(f"✅ Including entry with matching date: {entry_date}")
                    else:
                        print(f"⚠️ Filtered out entry with mismatched date: {entry_date} != {expected_notion_date}")
                except Exception as e:
                    print(f"❌ Date parsing error for {entry_date}: {e}")
                    # If we can't parse, exclude for safety
                    continue
            
            print(f"📊 Found {len(filtered_results)} entries with responses for {target_date}")
            return filtered_results
        else:
            print(f"Error fetching entries: {response.status_code} - {response.text}")
            return []
            
    except Exception as e:
        print(f"Error fetching entries with responses: {e}")
        return []

def extract_response_data(notion_entry):
    """Extract relevant data from Notion entry - UPDATED to include Discord User ID"""
    try:
        properties = notion_entry['properties']
        
        # Extract student name
        student_name = ""
        if 'Student Name' in properties and properties['Student Name']['title']:
            student_name = properties['Student Name']['title'][0]['text']['content']
        
        # Extract Discord User ID
        discord_user_id = ""
        if 'Discord User ID' in properties and properties['Discord User ID']['rich_text']:
            discord_user_id = properties['Discord User ID']['rich_text'][0]['text']['content']
        
        # Extract Discord Username (fallback)
        discord_username = ""
        if 'Discord Username' in properties and properties['Discord Username']['rich_text']:
            discord_username = properties['Discord Username']['rich_text'][0]['text']['content']
        
        # Extract Discord Display Name (fallback)
        discord_display_name = ""
        if 'Discord Display Name' in properties and properties['Discord Display Name']['rich_text']:
            discord_display_name = properties['Discord Display Name']['rich_text'][0]['text']['content']
        
        # Extract date
        entry_date = ""
        if 'Date' in properties and properties['Date']['date']:
            entry_date = properties['Date']['date']['start']
        
        # Extract CISO response
        ciso_response = ""
        if 'CISO Response' in properties and properties['CISO Response']['rich_text']:
            ciso_response = properties['CISO Response']['rich_text'][0]['text']['content']
        
        return {
            'entry_id': notion_entry['id'],
            'student_name': student_name,
            'discord_user_id': discord_user_id,
            'discord_username': discord_username,
            'discord_display_name': discord_display_name,
            'date': entry_date,
            'ciso_response': ciso_response
        }
        
    except Exception as e:
        print(f"Error extracting response data: {e}")
        return None

def verify_admin_code(provided_code):
    """Verify if the provided admin code is correct"""
    if not ADMIN_CODE:
        return False  # If no admin code is set, deny access
    return provided_code == ADMIN_CODE

async def require_admin_auth(ctx, provided_code):
    """Check admin authentication and send error message if invalid"""
    if not verify_admin_code(provided_code):
        await ctx.send("🚫 **Access Denied** - Invalid admin code. Contact your CISO for the correct authentication code.")
        return False
    return True
    """Mark a Notion entry as response sent"""
    try:
        update_data = {
            "properties": {
                "Response Sent": {
                    "checkbox": True
                },
                "Status": {
                    "select": {"name": "Responded"}
                }
            }
        }
        
        response = requests.patch(
            f'https://api.notion.com/v1/pages/{entry_id}',
            headers=NOTION_HEADERS,
            json=update_data
        )
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"Error marking response as sent: {e}")
        return False

async def send_ciso_response(response_data):
    """Send CISO response to student via DM - UPDATED to use Discord User ID"""
    try:
        user = None
        
        # Primary method: Use Discord User ID
        if response_data['discord_user_id']:
            try:
                user_id = int(response_data['discord_user_id'])
                user = bot.get_user(user_id)
                if not user:
                    # Try fetching if not in cache
                    user = await bot.fetch_user(user_id)
                print(f"✅ Found user by ID: {user.name} ({user_id})")
            except (ValueError, discord.NotFound) as e:
                print(f"⚠️ Could not find user by ID {response_data['discord_user_id']}: {e}")
        
        # Fallback method: Search by display name or username
        if not user:
            print(f"🔍 Falling back to name search for: {response_data['student_name']}")
            for guild in bot.guilds:
                for member in guild.members:
                    # Check multiple name variations
                    names_to_check = [
                        response_data['student_name'].lower(),
                        response_data['discord_display_name'].lower(),
                        response_data['discord_username'].lower()
                    ]
                    
                    member_names = [
                        member.display_name.lower(),
                        member.name.lower()
                    ]
                    
                    if any(name in member_names for name in names_to_check if name):
                        user = member
                        print(f"✅ Found user by name search: {user.name}")
                        break
                if user:
                    break
        
        if not user:
            print(f"❌ Could not find Discord user for: {response_data['student_name']} (ID: {response_data['discord_user_id']})")
            return False, f"User not found: {response_data['student_name']}"
        
        # Format the message
        message = f"""🛡️ **Message from your CISO - {CISO_NAME}**
*Delivered via Elliot Alderson Bot*

Hi {response_data['student_name']},

I've reviewed your journal entry from {response_data['date']}. Here's my personal feedback:

{response_data['ciso_response']}

Remember, I'm always here to support your cybersecurity journey. Feel free to reach out directly if you need immediate assistance.

Best regards,
{CISO_NAME}
Your CISO

---
*This message was delivered through Elliot Alderson, your CISO Bot Assistant*"""
        
        # Send DM
        await user.send(message)
        print(f"📤 Response sent successfully to {user.name}")
        return True, f"Message sent to {user.name}"
        
    except discord.Forbidden:
        error_msg = f"Cannot send DM to {response_data['student_name']} - DMs might be disabled"
        print(f"🚫 {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Error sending response to {response_data['student_name']}: {e}"
        print(f"❌ {error_msg}")
        return False, error_msg

@bot.event
async def on_ready():
    print(f'Bot is ready! Logged in as {bot.user.name} (ID: {bot.user.id})')
    print(f'Connected to {len(bot.guilds)} guilds')
    
    # Check if this is a reconnection (potential duplicate instance)
    if hasattr(bot, '_ready_called'):
        print("⚠️ WARNING: on_ready called multiple times - possible duplicate instance!")
        return
    
    bot._ready_called = True
    auto_send_daily_responses.start()

@tasks.loop(minutes=30)
async def auto_send_daily_responses():
    """Automatically send CISO responses at 18:00 SAST"""
    current_time = get_sa_time()
    
    # Check if it's 18:00 SAST (between 18:00-18:30 to avoid duplicates)
    if current_time.hour == 18 and current_time.minute < 30:
        current_date = current_time.strftime('%Y-%m-%d')
        
        print(f"🕕 18:00 SAST - Auto-sending daily CISO responses for {current_date}")
        
        # Get entries with responses for today
        entries = get_entries_with_responses(current_date)
        
        if not entries:
            print(f"📭 No pending CISO responses found for {current_date}")
            return
        
        sent_count = 0
        failed_count = 0
        failed_details = []
        
        print(f"📬 Found {len(entries)} pending responses to send...")
        
        for entry in entries:
            response_data = extract_response_data(entry)
            if not response_data:
                failed_count += 1
                failed_details.append("Failed to extract response data")
                continue
            
            # Send the response
            success, message = await send_ciso_response(response_data)
            
            if success:
                # Mark as sent in Notion
                if mark_response_sent(response_data['entry_id']):
                    sent_count += 1
                    print(f"✅ Auto-sent response to {response_data['student_name']}")
                else:
                    failed_count += 1
                    failed_details.append(f"{response_data['student_name']}: Failed to mark as sent in Notion")
                    print(f"❌ Failed to mark response as sent for {response_data['student_name']}")
            else:
                failed_count += 1
                failed_details.append(f"{response_data['student_name']}: {message}")
        
        # Log summary to console and include date verification
        print(f"📊 Auto-send complete for {current_date}: {sent_count} sent, {failed_count} failed")
        print(f"🔒 SAFETY: Only processed entries with date = {current_date}")
        
        # Optionally send summary to admin channel (if you want notifications)
        if CHANNEL_ID:
            channel = bot.get_channel(CHANNEL_ID)
            if channel and (sent_count > 0 or failed_count > 0):
                summary = f"""🤖 **Automated CISO Response Delivery - {current_date}**

✅ **Successfully sent:** {sent_count} responses
❌ **Failed:** {failed_count} responses
🔒 **Date Filter:** Only {current_date} entries processed

All available responses from {CISO_NAME} have been delivered automatically!"""
                
                if failed_count > 0 and len(failed_details) <= 3:
                    summary += f"\n\n**Failed Details:**\n" + "\n".join([f"• {detail}" for detail in failed_details])
                
                try:
                    await channel.send(summary)
                except Exception as e:
                    print(f"Failed to send auto-summary to channel: {e}")

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself (CRITICAL - prevents loops)
    if message.author == bot.user:
        return
    
    # Additional safety: ignore all bot messages
    if message.author.bot:
        return
    
    # Message deduplication check
    message_key = f"{message.id}_{message.author.id}_{message.content[:50]}"
    if message_key in processed_messages:
        print(f"🔄 Duplicate message detected and ignored from {message.author.name}")
        return
    
    # Add to processed messages cache
    processed_messages.add(message_key)
    
    # Clean cache if it gets too large
    if len(processed_messages) > MAX_PROCESSED_CACHE:
        # Remove oldest half
        processed_messages.clear()
        print("🧹 Cleared message deduplication cache")
    
    # Check if it's a DM or the specified channel
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_target_channel = CHANNEL_ID and message.channel.id == CHANNEL_ID
    
    # Only process CISO updates from DMs or the target channel
    if not (is_dm or is_target_channel or CHANNEL_ID is None):
        await bot.process_commands(message)
        return
    
    # Check if message starts with "Daily CISO Update"
    if message.content.lower().startswith('daily ciso update'):
        message_type = "DM" if is_dm else "channel"
        print(f"CISO update detected from {message.author.name} (ID: {message.author.id}) via {message_type}")
        
        # Parse the message - UPDATED to pass author object
        parsed_data = parse_ciso_update(message.content, message.author)
        
        if parsed_data:
            # Create Notion entry
            success, result_message = create_notion_entry(parsed_data)
            
            if success:
                # React with checkmark and send confirmation
                await message.add_reaction('✅')
                
                # Send detailed confirmation in DMs
                if is_dm:
                    confirmation_msg = f"""
**CISO Update Processed Successfully!** ✅

**Student:** {parsed_data['student_name']}
**Discord ID:** {parsed_data['discord_user_id']}
**Date:** {parsed_data['date']}
**Hours:** {parsed_data['hours_worked']}

Your journal entry has been recorded in the database with your Discord information for reliable message delivery. I'll review it and may send you personalized feedback later today.

Keep up the excellent work on your cybersecurity journey! 🎯

*- Elliot Alderson, CISO Bot Assistant*
                    """
                    await message.channel.send(confirmation_msg)
                
                print(f"Successfully processed update for {parsed_data['student_name']} (ID: {parsed_data['discord_user_id']}) via {message_type}")
                
            else:
                # React with X to indicate error
                await message.add_reaction('❌')
                
                # Send error details in DMs
                if is_dm:
                    error_msg = f"""
**Error Processing Update** ❌

There was an issue saving your journal entry to the database:
`{result_message}`

Please try again or contact your instructor if the problem persists.
                    """
                    await message.channel.send(error_msg)
                
                print(f"Failed to process update: {result_message}")
                
        else:
            # React with warning for parsing issues
            await message.add_reaction('⚠️')
            
            # Send helpful formatting reminder in DMs
            if is_dm:
                format_help = f"""
**Format Issue Detected** ⚠️

I couldn't parse your journal entry. Please make sure it follows this format:

```
Daily CISO Update - [Date]
Student: [Your Name]
Hours Worked: [Number]
Completed Today:
- [Your tasks]

Current Findings/Issues:
- [Your findings]

Tomorrow's Plan:
- [Your plans]

CISO Input Needed:
- [Your questions]
```

Try sending it again with the correct format! 📝
                """
                await message.channel.send(format_help)
            
            print(f"Failed to parse CISO update message from {message.author.name}")
    
    # Process other commands
    await bot.process_commands(message)

@bot.command(name='send_responses')
async def send_daily_responses(ctx, admin_code: str = None, date: str = None):
    """Send all pending CISO responses for a specific date - ADMIN ONLY"""
    
    # Check admin authentication
    if not await require_admin_auth(ctx, admin_code):
        return
    
    if date is None:
        date = get_sa_date().strftime('%Y-%m-%d')
    
    await ctx.send(f"🔍 Checking for pending CISO responses for {date}...")
    
    # Get entries with responses
    entries = get_entries_with_responses(date)
    
    if not entries:
        await ctx.send(f"📭 No pending responses found for {date}")
        return
    
    sent_count = 0
    failed_count = 0
    failed_details = []
    
    for entry in entries:
        response_data = extract_response_data(entry)
        if not response_data:
            failed_count += 1
            failed_details.append("Failed to extract response data")
            continue
        
        # Send the response - UPDATED function call
        success, message = await send_ciso_response(response_data)
        
        if success:
            # Mark as sent in Notion
            if mark_response_sent(response_data['entry_id']):
                sent_count += 1
                print(f"✅ Response sent to {response_data['student_name']}")
            else:
                failed_count += 1
                failed_details.append(f"{response_data['student_name']}: Failed to mark as sent in Notion")
                print(f"❌ Failed to mark response as sent for {response_data['student_name']}")
        else:
            failed_count += 1
            failed_details.append(f"{response_data['student_name']}: {message}")
    
    # Send summary
    summary = f"""📊 **Response Sending Complete**

✅ **Successfully sent:** {sent_count} responses
❌ **Failed:** {failed_count} responses
📅 **Date:** {date}

All successful responses have been delivered from {CISO_NAME}!"""
    
    if failed_details:
        summary += f"\n\n**Failed Details:**\n" + "\n".join([f"• {detail}" for detail in failed_details[:5]])
        if len(failed_details) > 5:
            summary += f"\n• ... and {len(failed_details) - 5} more"
    
    await ctx.send(summary)

@bot.command(name='preview_responses')
async def preview_responses(ctx, admin_code: str = None, date: str = None):
    """Preview pending CISO responses without sending them - ADMIN ONLY"""
    
    # Check admin authentication
    if not await require_admin_auth(ctx, admin_code):
        return
    
    if date is None:
        date = get_sa_date().strftime('%Y-%m-%d')
    
    entries = get_entries_with_responses(date)
    
    if not entries:
        await ctx.send(f"📭 No pending responses found for {date}")
        return
    
    preview_msg = f"📋 **Response Preview for {date}**\n\n"
    
    for i, entry in enumerate(entries, 1):
        response_data = extract_response_data(entry)
        if response_data:
            discord_info = f"(ID: {response_data['discord_user_id'][:8]}...)" if response_data['discord_user_id'] else "(No ID stored)"
            preview_msg += f"**{i}. {response_data['student_name']}** {discord_info}\n"
            preview_msg += f"Response: {response_data['ciso_response'][:100]}{'...' if len(response_data['ciso_response']) > 100 else ''}\n\n"
    
    # Discord has message length limits, so split if needed
    if len(preview_msg) > 2000:
        preview_msg = preview_msg[:1900] + "\n\n*... (truncated for length)*"
    
    await ctx.send(preview_msg)
    await ctx.send(f"📬 Ready to send {len(entries)} responses. Use `!send_responses [admin_code]` to send them.")

@bot.command(name='response_count')
async def response_count(ctx, admin_code: str = None, date: str = None):
    """Show count of pending responses for a specific date - ADMIN ONLY"""
    
    # Check admin authentication
    if not await require_admin_auth(ctx, admin_code):
        return
    
    if date is None:
        date = get_sa_date().strftime('%Y-%m-%d')
    
    entries = get_entries_with_responses(date)
    count = len(entries)
    
    if count == 0:
        await ctx.send(f"📭 No pending responses for {date}")
    else:
        await ctx.send(f"📬 **{count}** pending responses ready to send for {date}")

@bot.command(name='debug_dates')
async def debug_dates(ctx, admin_code: str = None):
    """Debug date matching issues - ADMIN ONLY"""
    
    # Check admin authentication
    if not await require_admin_auth(ctx, admin_code):
        return
    
    await ctx.send("🔍 **Debugging Date Matching**")
    
    try:
        current_date = get_sa_date().strftime('%Y-%m-%d')
        await ctx.send(f"📅 **Current SA Date:** {current_date}")
        
        # Query ALL entries regardless of date to see what's in the database
        query_data = {
            "filter": {
                "and": [
                    {
                        "property": "CISO Response",
                        "rich_text": {
                            "is_not_empty": True
                        }
                    },
                    {
                        "property": "Response Sent",
                        "checkbox": {
                            "equals": False
                        }
                    }
                ]
            },
            "sorts": [
                {
                    "property": "Date",
                    "direction": "descending"
                }
            ]
        }
        
        response = requests.post(
            f'https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query',
            headers=NOTION_HEADERS,
            json=query_data
        )
        
        if response.status_code == 200:
            results = response.json()['results']
            
            if not results:
                await ctx.send("📭 No entries with CISO responses found in database")
                return
            
            debug_msg = f"🗃️ **Found {len(results)} entries with responses:**\n\n"
            
            for i, entry in enumerate(results[:5], 1):  # Show max 5 entries
                properties = entry['properties']
                
                # Extract data
                student_name = ""
                if 'Student Name' in properties and properties['Student Name']['title']:
                    student_name = properties['Student Name']['title'][0]['text']['content']
                
                entry_date = ""
                if 'Date' in properties and properties['Date']['date']:
                    entry_date = properties['Date']['date']['start']
                
                response_sent = False
                if 'Response Sent' in properties:
                    response_sent = properties['Response Sent']['checkbox']
                
                # Check if date matches today
                date_matches = entry_date == current_date
                match_emoji = "✅" if date_matches else "❌"
                
                debug_msg += f"**{i}. {student_name}**\n"
                debug_msg += f"Date: `{entry_date}` {match_emoji}\n"
                debug_msg += f"Response Sent: {response_sent}\n"
                debug_msg += f"Matches Today: {date_matches}\n\n"
            
            if len(results) > 5:
                debug_msg += f"... and {len(results) - 5} more entries"
            
            # Split message if too long
            if len(debug_msg) > 2000:
                debug_msg = debug_msg[:1900] + "\n\n*... (truncated)*"
            
            await ctx.send(debug_msg)
            
        else:
            await ctx.send(f"❌ **Error querying database:** {response.status_code}")
            
    except Exception as e:
        await ctx.send(f"❌ **Debug error:** {str(e)}")

@bot.command(name='send_reminder')
async def send_journal_reminder(ctx):
    """Manually send journal submission reminder"""
    current_time = get_sa_time()
    
    reminder_msg = f"""@everyone It's time for your daily CISO update! Please use the following format:

Daily CISO Update - {current_time.strftime('%Y-%m-%d')}
Student: [Your Name]
Hours Worked: [Number]
Completed Today:
[List what you completed today]

Current Findings/Issues:
[List any findings or issues]

Tomorrow's Plan:
[List your plan for tomorrow]

CISO Input Needed:
[List any questions or input needed from the CISO]"""
    
    await ctx.send(reminder_msg)
    await ctx.send("📝 Journal submission reminder sent!")
    """Test user lookup by Discord ID"""
    if not user_id:
        await ctx.send("Please provide a Discord User ID to test. Usage: `!test_user 123456789`")
        return
    
    try:
        user_id_int = int(user_id)
        user = bot.get_user(user_id_int)
        
        if not user:
            user = await bot.fetch_user(user_id_int)
        
        if user:
            await ctx.send(f"✅ **User Found!**\n**Name:** {user.name}\n**Display Name:** {user.display_name}\n**ID:** {user.id}")
        else:
            await ctx.send(f"❌ User with ID {user_id} not found")
            
    except ValueError:
        await ctx.send(f"❌ Invalid user ID format: {user_id}")
    except discord.NotFound:
        await ctx.send(f"❌ User with ID {user_id} not found")
    except Exception as e:
        await ctx.send(f"❌ Error looking up user: {e}")

@bot.command(name='test')
async def test_bot(ctx):
    """Test command to verify bot is working"""
    await ctx.send("Elliot Alderson (CISO Bot) is online and monitoring! ✅\n*Ready to process journals with Discord User ID tracking and send CISO responses.*")

@bot.command(name='format')
async def format_command(ctx):
    """Show help message with journal format"""
    help_msg = f"""
**Elliot Alderson - CISO Bot Help** 📚

**How to Submit Your Journal:**
You can send your daily journal update in two ways:
1. **Direct Message** - Send me a private message with your update
2. **Channel** - Post in the designated channel (if configured)

**Required Format:**
```
Daily CISO Update - [Date]
Student: [Your Name]
Hours Worked: [Number]
Completed Today:
- [List your completed tasks]

Current Findings/Issues:
- [Any technical findings or blockers]

Tomorrow's Plan:
- [Your objectives for tomorrow]

CISO Input Needed:
- [Questions or guidance you need]
```

**New Feature: Discord ID Tracking** 🆔
Your Discord User ID is now automatically stored for reliable message delivery!

**Bot Reactions:**
✅ - Successfully processed and saved to database
❌ - Error occurred while saving
⚠️ - Format issue detected, please check your formatting

**Commands:**
- `!test` - Test if bot is responding
- `!test_user [user_id]` - Test Discord user lookup
- `!send_responses [admin_code] [date]` - Send pending CISO responses (ADMIN ONLY)
- `!preview_responses [admin_code] [date]` - Preview pending responses (ADMIN ONLY)
- `!response_count [admin_code] [date]` - Check response count (ADMIN ONLY)
- `!send_reminder` - Send journal submission reminder
- `!help` - Show this help message

**Example Journal Entry:**
```
Daily CISO Update - 2025-06-12
Student: John Smith
Hours Worked: 8
Completed Today:
- Configured firewall rules for DMZ
- Analyzed network traffic logs
- Completed SIEM dashboard setup

Current Findings/Issues:
- Detected unusual port scanning activity
- Need clarification on incident response procedures

Tomorrow's Plan:
- Investigate port scanning source
- Update security policies documentation
- Begin penetration testing phase

CISO Input Needed:
- Should we block the suspicious IP immediately?
- What's the escalation process for security incidents?
```

Happy journaling with improved reliability! 🛡️

*- Elliot Alderson, CISO Bot Assistant*
    """
    await ctx.send(help_msg)

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return  # Ignore unknown commands
    print(f'Error: {error}')

if __name__ == '__main__':
    # Verify required environment variables
    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_TOKEN environment variable not set")
        exit(1)
    if not NOTION_TOKEN:
        print("ERROR: NOTION_TOKEN environment variable not set")
        exit(1)
    if not NOTION_DATABASE_ID:
        print("ERROR: NOTION_DATABASE_ID environment variable not set")
        exit(1)
    if not ADMIN_CODE:
        print("WARNING: ADMIN_CODE environment variable not set - admin commands will be disabled")
    
    print("🚀 Starting Enhanced CISO Bot with Discord User ID tracking...")
    print(f"🔐 Admin protection: {'ENABLED' if ADMIN_CODE else 'DISABLED'}")
    
    # Start the bot
    bot.run(DISCORD_TOKEN)
        ciso_match = re.search(ciso_pattern, message_content, re.DOTALL | re.IGNORECASE)
        ciso_input = ciso_match.group(1).strip() if ciso_match else ""
        
        return {
            'date': date_str,
            'student_name': student_name,
            'discord_user_id': str(author.id),  # Store Discord User ID
            'discord_username': author.name,    # Store Discord username for reference
            'discord_display_name': author.display_name or author.name,  # Store display name
            'hours_worked': hours_worked,
            'completed_today': completed_today,
            'current_findings': current_findings,
            'tomorrow_plan': tomorrow_plan,
            'ciso_input': ciso_input
        }
    except Exception as e:
        print(f"Error parsing message: {e}")
        return None

def create_notion_entry(parsed_data):
    """Create a new entry in the Notion database"""
    try:
        # Parse date string to ISO format for Notion
        try:
            parsed_date = datetime.strptime(parsed_data['date'], '%Y-%m-%d')
            # Convert to SAST timezone
            parsed_date = SAST.localize(parsed_date)
        except:
            # Try different date formats
            try:
                parsed_date = datetime.strptime(parsed_data['date'], '%m/%d/%Y')
                parsed_date = SAST.localize(parsed_date)
            except:
                parsed_date = get_sa_time()
        
        # Notion database entry structure - UPDATED with Discord fields
        data = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": {
                "Date": {
                    "date": {"start": parsed_date.strftime('%Y-%m-%d')}
                },
                "Student Name": {
                    "title": [{"text": {"content": parsed_data['student_name']}}]
                },
                "Discord User ID": {
                    "rich_text": [{"text": {"content": parsed_data['discord_user_id']}}]
                },
                "Discord Username": {
                    "rich_text": [{"text": {"content": parsed_data['discord_username']}}]
                },
                "Discord Display Name": {
                    "rich_text": [{"text": {"content": parsed_data['discord_display_name']}}]
                },
                "Hours Worked": {
                    "number": parsed_data['hours_worked']
                },
                "Completed Today": {
                    "rich_text": [{"text": {"content": parsed_data['completed_today'][:2000]}}]  # Notion has character limits
                },
                "Current Findings": {
                    "rich_text": [{"text": {"content": parsed_data['current_findings'][:2000]}}]
                },
                "Tomorrow Plan": {
                    "rich_text": [{"text": {"content": parsed_data['tomorrow_plan'][:2000]}}]
                },
                "CISO Input Needed": {
                    "rich_text": [{"text": {"content": parsed_data['ciso_input'][:2000]}}]
                },
                "CISO Response": {
                    "rich_text": [{"text": {"content": ""}}]  # Empty field for CISO to fill
                },
                "Response Sent": {
                    "checkbox": False  # Track if response has been sent
                },
                "Status": {
                    "select": {"name": "New"}
                }
            }
        }
        
        # Send to Notion API
        response = requests.post(
            'https://api.notion.com/v1/pages',
            headers=NOTION_HEADERS,
            json=data
        )
        
        if response.status_code == 200:
            return True, "Entry created successfully"
        else:
            return False, f"Notion API error: {response.status_code} - {response.text}"
            
    except Exception as e:
        return False, f"Error creating Notion entry: {e}"

def get_entries_with_responses(target_date=None):
    """Fetch Notion entries that have CISO responses but haven't been sent yet"""
    try:
        if target_date is None:
            target_date = get_sa_date().strftime('%Y-%m-%d')
        
        # Query Notion database for entries with responses - ONLY for the specific date
        query_data = {
            "filter": {
                "and": [
                    {
                        "property": "Date",
                        "date": {
                            "equals": target_date  # STRICT date matching
                        }
                    },
                    {
                        "property": "CISO Response",
                        "rich_text": {
                            "is_not_empty": True
                        }
                    },
                    {
                        "property": "Response Sent",
                        "checkbox": {
                            "equals": False
                        }
                    }
                ]
            },
            "sorts": [
                {
                    "property": "Student Name",
                    "direction": "ascending"
                }
            ]
        }
        
        response = requests.post(
            f'https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query',
            headers=NOTION_HEADERS,
            json=query_data
        )
        
        if response.status_code == 200:
            results = response.json()['results']
            
            # ADDITIONAL SAFETY CHECK: Double-verify the date matches
            filtered_results = []
            for entry in results:
                entry_date = ""
                if 'Date' in entry['properties'] and entry['properties']['Date']['date']:
                    entry_date = entry['properties']['Date']['date']['start']
                
                # Convert target_date to match Notion's format for comparison
                try:
                    # Parse target_date (YYYY-MM-DD) and convert to Notion's format
                    target_dt = datetime.strptime(target_date, '%Y-%m-%d')
                    # Notion stores dates in YYYY-MM-DD format in the API
                    expected_notion_date = target_dt.strftime('%Y-%m-%d')
                    
                    # Only include if date exactly matches target date
                    if entry_date == expected_notion_date:
                        filtered_results.append(entry)
                        print(f"✅ Including entry with matching date: {entry_date}")
                    else:
                        print(f"⚠️ Filtered out entry with mismatched date: {entry_date} != {expected_notion_date}")
                except Exception as e:
                    print(f"❌ Date parsing error for {entry_date}: {e}")
                    # If we can't parse, exclude for safety
                    continue
            
            print(f"📊 Found {len(filtered_results)} entries with responses for {target_date}")
            return filtered_results
        else:
            print(f"Error fetching entries: {response.status_code} - {response.text}")
            return []
            
    except Exception as e:
        print(f"Error fetching entries with responses: {e}")
        return []

def extract_response_data(notion_entry):
    """Extract relevant data from Notion entry - UPDATED to include Discord User ID"""
    try:
        properties = notion_entry['properties']
        
        # Extract student name
        student_name = ""
        if 'Student Name' in properties and properties['Student Name']['title']:
            student_name = properties['Student Name']['title'][0]['text']['content']
        
        # Extract Discord User ID
        discord_user_id = ""
        if 'Discord User ID' in properties and properties['Discord User ID']['rich_text']:
            discord_user_id = properties['Discord User ID']['rich_text'][0]['text']['content']
        
        # Extract Discord Username (fallback)
        discord_username = ""
        if 'Discord Username' in properties and properties['Discord Username']['rich_text']:
            discord_username = properties['Discord Username']['rich_text'][0]['text']['content']
        
        # Extract Discord Display Name (fallback)
        discord_display_name = ""
        if 'Discord Display Name' in properties and properties['Discord Display Name']['rich_text']:
            discord_display_name = properties['Discord Display Name']['rich_text'][0]['text']['content']
        
        # Extract date
        entry_date = ""
        if 'Date' in properties and properties['Date']['date']:
            entry_date = properties['Date']['date']['start']
        
        # Extract CISO response
        ciso_response = ""
        if 'CISO Response' in properties and properties['CISO Response']['rich_text']:
            ciso_response = properties['CISO Response']['rich_text'][0]['text']['content']
        
        return {
            'entry_id': notion_entry['id'],
            'student_name': student_name,
            'discord_user_id': discord_user_id,
            'discord_username': discord_username,
            'discord_display_name': discord_display_name,
            'date': entry_date,
            'ciso_response': ciso_response
        }
        
    except Exception as e:
        print(f"Error extracting response data: {e}")
        return None

def verify_admin_code(provided_code):
    """Verify if the provided admin code is correct"""
    if not ADMIN_CODE:
        return False  # If no admin code is set, deny access
    return provided_code == ADMIN_CODE

async def require_admin_auth(ctx, provided_code):
    """Check admin authentication and send error message if invalid"""
    if not verify_admin_code(provided_code):
        await ctx.send("🚫 **Access Denied** - Invalid admin code. Contact your CISO for the correct authentication code.")
        return False
    return True
    """Mark a Notion entry as response sent"""
    try:
        update_data = {
            "properties": {
                "Response Sent": {
                    "checkbox": True
                },
                "Status": {
                    "select": {"name": "Responded"}
                }
            }
        }
        
        response = requests.patch(
            f'https://api.notion.com/v1/pages/{entry_id}',
            headers=NOTION_HEADERS,
            json=update_data
        )
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"Error marking response as sent: {e}")
        return False

async def send_ciso_response(response_data):
    """Send CISO response to student via DM - UPDATED to use Discord User ID"""
    try:
        user = None
        
        # Primary method: Use Discord User ID
        if response_data['discord_user_id']:
            try:
                user_id = int(response_data['discord_user_id'])
                user = bot.get_user(user_id)
                if not user:
                    # Try fetching if not in cache
                    user = await bot.fetch_user(user_id)
                print(f"✅ Found user by ID: {user.name} ({user_id})")
            except (ValueError, discord.NotFound) as e:
                print(f"⚠️ Could not find user by ID {response_data['discord_user_id']}: {e}")
        
        # Fallback method: Search by display name or username
        if not user:
            print(f"🔍 Falling back to name search for: {response_data['student_name']}")
            for guild in bot.guilds:
                for member in guild.members:
                    # Check multiple name variations
                    names_to_check = [
                        response_data['student_name'].lower(),
                        response_data['discord_display_name'].lower(),
                        response_data['discord_username'].lower()
                    ]
                    
                    member_names = [
                        member.display_name.lower(),
                        member.name.lower()
                    ]
                    
                    if any(name in member_names for name in names_to_check if name):
                        user = member
                        print(f"✅ Found user by name search: {user.name}")
                        break
                if user:
                    break
        
        if not user:
            print(f"❌ Could not find Discord user for: {response_data['student_name']} (ID: {response_data['discord_user_id']})")
            return False, f"User not found: {response_data['student_name']}"
        
        # Format the message
        message = f"""🛡️ **Message from your CISO - {CISO_NAME}**
*Delivered via Elliot Alderson Bot*

Hi {response_data['student_name']},

I've reviewed your journal entry from {response_data['date']}. Here's my personal feedback:

{response_data['ciso_response']}

Remember, I'm always here to support your cybersecurity journey. Feel free to reach out directly if you need immediate assistance.

Best regards,
{CISO_NAME}
Your CISO

---
*This message was delivered through Elliot Alderson, your CISO Bot Assistant*"""
        
        # Send DM
        await user.send(message)
        print(f"📤 Response sent successfully to {user.name}")
        return True, f"Message sent to {user.name}"
        
    except discord.Forbidden:
        error_msg = f"Cannot send DM to {response_data['student_name']} - DMs might be disabled"
        print(f"🚫 {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Error sending response to {response_data['student_name']}: {e}"
        print(f"❌ {error_msg}")
        return False, error_msg

@bot.event
async def on_ready():
    print(f'Bot is ready! Logged in as {bot.user.name} (ID: {bot.user.id})')
    print(f'Connected to {len(bot.guilds)} guilds')
    
    # Check if this is a reconnection (potential duplicate instance)
    if hasattr(bot, '_ready_called'):
        print("⚠️ WARNING: on_ready called multiple times - possible duplicate instance!")
        return
    
    bot._ready_called = True
    auto_send_daily_responses.start()

@tasks.loop(minutes=30)
async def auto_send_daily_responses():
    """Automatically send CISO responses at 18:00 SAST"""
    current_time = get_sa_time()
    
    # Check if it's 18:00 SAST (between 18:00-18:30 to avoid duplicates)
    if current_time.hour == 18 and current_time.minute < 30:
        current_date = current_time.strftime('%Y-%m-%d')
        
        print(f"🕕 18:00 SAST - Auto-sending daily CISO responses for {current_date}")
        
        # Get entries with responses for today
        entries = get_entries_with_responses(current_date)
        
        if not entries:
            print(f"📭 No pending CISO responses found for {current_date}")
            return
        
        sent_count = 0
        failed_count = 0
        failed_details = []
        
        print(f"📬 Found {len(entries)} pending responses to send...")
        
        for entry in entries:
            response_data = extract_response_data(entry)
            if not response_data:
                failed_count += 1
                failed_details.append("Failed to extract response data")
                continue
            
            # Send the response
            success, message = await send_ciso_response(response_data)
            
            if success:
                # Mark as sent in Notion
                if mark_response_sent(response_data['entry_id']):
                    sent_count += 1
                    print(f"✅ Auto-sent response to {response_data['student_name']}")
                else:
                    failed_count += 1
                    failed_details.append(f"{response_data['student_name']}: Failed to mark as sent in Notion")
                    print(f"❌ Failed to mark response as sent for {response_data['student_name']}")
            else:
                failed_count += 1
                failed_details.append(f"{response_data['student_name']}: {message}")
        
        # Log summary to console and include date verification
        print(f"📊 Auto-send complete for {current_date}: {sent_count} sent, {failed_count} failed")
        print(f"🔒 SAFETY: Only processed entries with date = {current_date}")
        
        # Optionally send summary to admin channel (if you want notifications)
        if CHANNEL_ID:
            channel = bot.get_channel(CHANNEL_ID)
            if channel and (sent_count > 0 or failed_count > 0):
                summary = f"""🤖 **Automated CISO Response Delivery - {current_date}**

✅ **Successfully sent:** {sent_count} responses
❌ **Failed:** {failed_count} responses
🔒 **Date Filter:** Only {current_date} entries processed

All available responses from {CISO_NAME} have been delivered automatically!"""
                
                if failed_count > 0 and len(failed_details) <= 3:
                    summary += f"\n\n**Failed Details:**\n" + "\n".join([f"• {detail}" for detail in failed_details])
                
                try:
                    await channel.send(summary)
                except Exception as e:
                    print(f"Failed to send auto-summary to channel: {e}")

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself (CRITICAL - prevents loops)
    if message.author == bot.user:
        return
    
    # Additional safety: ignore all bot messages
    if message.author.bot:
        return
    
    # Message deduplication check
    message_key = f"{message.id}_{message.author.id}_{message.content[:50]}"
    if message_key in processed_messages:
        print(f"🔄 Duplicate message detected and ignored from {message.author.name}")
        return
    
    # Add to processed messages cache
    processed_messages.add(message_key)
    
    # Clean cache if it gets too large
    if len(processed_messages) > MAX_PROCESSED_CACHE:
        # Remove oldest half
        processed_messages.clear()
        print("🧹 Cleared message deduplication cache")
    
    # Check if it's a DM or the specified channel
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_target_channel = CHANNEL_ID and message.channel.id == CHANNEL_ID
    
    # Only process CISO updates from DMs or the target channel
    if not (is_dm or is_target_channel or CHANNEL_ID is None):
        await bot.process_commands(message)
        return
    
    # Check if message starts with "Daily CISO Update"
    if message.content.lower().startswith('daily ciso update'):
        message_type = "DM" if is_dm else "channel"
        print(f"CISO update detected from {message.author.name} (ID: {message.author.id}) via {message_type}")
        
        # Parse the message - UPDATED to pass author object
        parsed_data = parse_ciso_update(message.content, message.author)
        
        if parsed_data:
            # Create Notion entry
            success, result_message = create_notion_entry(parsed_data)
            
            if success:
                # React with checkmark and send confirmation
                await message.add_reaction('✅')
                
                # Send detailed confirmation in DMs
                if is_dm:
                    confirmation_msg = f"""
**CISO Update Processed Successfully!** ✅

**Student:** {parsed_data['student_name']}
**Discord ID:** {parsed_data['discord_user_id']}
**Date:** {parsed_data['date']}
**Hours:** {parsed_data['hours_worked']}

Your journal entry has been recorded in the database with your Discord information for reliable message delivery. I'll review it and may send you personalized feedback later today.

Keep up the excellent work on your cybersecurity journey! 🎯

*- Elliot Alderson, CISO Bot Assistant*
                    """
                    await message.channel.send(confirmation_msg)
                
                print(f"Successfully processed update for {parsed_data['student_name']} (ID: {parsed_data['discord_user_id']}) via {message_type}")
                
            else:
                # React with X to indicate error
                await message.add_reaction('❌')
                
                # Send error details in DMs
                if is_dm:
                    error_msg = f"""
**Error Processing Update** ❌

There was an issue saving your journal entry to the database:
`{result_message}`

Please try again or contact your instructor if the problem persists.
                    """
                    await message.channel.send(error_msg)
                
                print(f"Failed to process update: {result_message}")
                
        else:
            # React with warning for parsing issues
            await message.add_reaction('⚠️')
            
            # Send helpful formatting reminder in DMs
            if is_dm:
                format_help = f"""
**Format Issue Detected** ⚠️

I couldn't parse your journal entry. Please make sure it follows this format:

```
Daily CISO Update - [Date]
Student: [Your Name]
Hours Worked: [Number]
Completed Today:
- [Your tasks]

Current Findings/Issues:
- [Your findings]

Tomorrow's Plan:
- [Your plans]

CISO Input Needed:
- [Your questions]
```

Try sending it again with the correct format! 📝
                """
                await message.channel.send(format_help)
            
            print(f"Failed to parse CISO update message from {message.author.name}")
    
    # Process other commands
    await bot.process_commands(message)

@bot.command(name='send_responses')
async def send_daily_responses(ctx, admin_code: str = None, date: str = None):
    """Send all pending CISO responses for a specific date - ADMIN ONLY"""
    
    # Check admin authentication
    if not await require_admin_auth(ctx, admin_code):
        return
    
    if date is None:
        date = get_sa_date().strftime('%Y-%m-%d')
    
    await ctx.send(f"🔍 Checking for pending CISO responses for {date}...")
    
    # Get entries with responses
    entries = get_entries_with_responses(date)
    
    if not entries:
        await ctx.send(f"📭 No pending responses found for {date}")
        return
    
    sent_count = 0
    failed_count = 0
    failed_details = []
    
    for entry in entries:
        response_data = extract_response_data(entry)
        if not response_data:
            failed_count += 1
            failed_details.append("Failed to extract response data")
            continue
        
        # Send the response - UPDATED function call
        success, message = await send_ciso_response(response_data)
        
        if success:
            # Mark as sent in Notion
            if mark_response_sent(response_data['entry_id']):
                sent_count += 1
                print(f"✅ Response sent to {response_data['student_name']}")
            else:
                failed_count += 1
                failed_details.append(f"{response_data['student_name']}: Failed to mark as sent in Notion")
                print(f"❌ Failed to mark response as sent for {response_data['student_name']}")
        else:
            failed_count += 1
            failed_details.append(f"{response_data['student_name']}: {message}")
    
    # Send summary
    summary = f"""📊 **Response Sending Complete**

✅ **Successfully sent:** {sent_count} responses
❌ **Failed:** {failed_count} responses
📅 **Date:** {date}

All successful responses have been delivered from {CISO_NAME}!"""
    
    if failed_details:
        summary += f"\n\n**Failed Details:**\n" + "\n".join([f"• {detail}" for detail in failed_details[:5]])
        if len(failed_details) > 5:
            summary += f"\n• ... and {len(failed_details) - 5} more"
    
    await ctx.send(summary)

@bot.command(name='preview_responses')
async def preview_responses(ctx, admin_code: str = None, date: str = None):
    """Preview pending CISO responses without sending them - ADMIN ONLY"""
    
    # Check admin authentication
    if not await require_admin_auth(ctx, admin_code):
        return
    
    if date is None:
        date = get_sa_date().strftime('%Y-%m-%d')
    
    entries = get_entries_with_responses(date)
    
    if not entries:
        await ctx.send(f"📭 No pending responses found for {date}")
        return
    
    preview_msg = f"📋 **Response Preview for {date}**\n\n"
    
    for i, entry in enumerate(entries, 1):
        response_data = extract_response_data(entry)
        if response_data:
            discord_info = f"(ID: {response_data['discord_user_id'][:8]}...)" if response_data['discord_user_id'] else "(No ID stored)"
            preview_msg += f"**{i}. {response_data['student_name']}** {discord_info}\n"
            preview_msg += f"Response: {response_data['ciso_response'][:100]}{'...' if len(response_data['ciso_response']) > 100 else ''}\n\n"
    
    # Discord has message length limits, so split if needed
    if len(preview_msg) > 2000:
        preview_msg = preview_msg[:1900] + "\n\n*... (truncated for length)*"
    
    await ctx.send(preview_msg)
    await ctx.send(f"📬 Ready to send {len(entries)} responses. Use `!send_responses [admin_code]` to send them.")

@bot.command(name='response_count')
async def response_count(ctx, admin_code: str = None, date: str = None):
    """Show count of pending responses for a specific date - ADMIN ONLY"""
    
    # Check admin authentication
    if not await require_admin_auth(ctx, admin_code):
        return
    
    if date is None:
        date = get_sa_date().strftime('%Y-%m-%d')
    
    entries = get_entries_with_responses(date)
    count = len(entries)
    
    if count == 0:
        await ctx.send(f"📭 No pending responses for {date}")
    else:
        await ctx.send(f"📬 **{count}** pending responses ready to send for {date}")

@bot.command(name='debug_dates')
async def debug_dates(ctx, admin_code: str = None):
    """Debug date matching issues - ADMIN ONLY"""
    
    # Check admin authentication
    if not await require_admin_auth(ctx, admin_code):
        return
    
    await ctx.send("🔍 **Debugging Date Matching**")
    
    try:
        current_date = get_sa_date().strftime('%Y-%m-%d')
        await ctx.send(f"📅 **Current SA Date:** {current_date}")
        
        # Query ALL entries regardless of date to see what's in the database
        query_data = {
            "filter": {
                "and": [
                    {
                        "property": "CISO Response",
                        "rich_text": {
                            "is_not_empty": True
                        }
                    },
                    {
                        "property": "Response Sent",
                        "checkbox": {
                            "equals": False
                        }
                    }
                ]
            },
            "sorts": [
                {
                    "property": "Date",
                    "direction": "descending"
                }
            ]
        }
        
        response = requests.post(
            f'https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query',
            headers=NOTION_HEADERS,
            json=query_data
        )
        
        if response.status_code == 200:
            results = response.json()['results']
            
            if not results:
                await ctx.send("📭 No entries with CISO responses found in database")
                return
            
            debug_msg = f"🗃️ **Found {len(results)} entries with responses:**\n\n"
            
            for i, entry in enumerate(results[:5], 1):  # Show max 5 entries
                properties = entry['properties']
                
                # Extract data
                student_name = ""
                if 'Student Name' in properties and properties['Student Name']['title']:
                    student_name = properties['Student Name']['title'][0]['text']['content']
                
                entry_date = ""
                if 'Date' in properties and properties['Date']['date']:
                    entry_date = properties['Date']['date']['start']
                
                response_sent = False
                if 'Response Sent' in properties:
                    response_sent = properties['Response Sent']['checkbox']
                
                # Check if date matches today
                date_matches = entry_date == current_date
                match_emoji = "✅" if date_matches else "❌"
                
                debug_msg += f"**{i}. {student_name}**\n"
                debug_msg += f"Date: `{entry_date}` {match_emoji}\n"
                debug_msg += f"Response Sent: {response_sent}\n"
                debug_msg += f"Matches Today: {date_matches}\n\n"
            
            if len(results) > 5:
                debug_msg += f"... and {len(results) - 5} more entries"
            
            # Split message if too long
            if len(debug_msg) > 2000:
                debug_msg = debug_msg[:1900] + "\n\n*... (truncated)*"
            
            await ctx.send(debug_msg)
            
        else:
            await ctx.send(f"❌ **Error querying database:** {response.status_code}")
            
    except Exception as e:
        await ctx.send(f"❌ **Debug error:** {str(e)}")

@bot.command(name='send_reminder')
async def send_journal_reminder(ctx):
    """Manually send journal submission reminder"""
    current_time = get_sa_time()
    
    reminder_msg = f"""@everyone It's time for your daily CISO update! Please use the following format:

Daily CISO Update - {current_time.strftime('%Y-%m-%d')}
Student: [Your Name]
Hours Worked: [Number]
Completed Today:
[List what you completed today]

Current Findings/Issues:
[List any findings or issues]

Tomorrow's Plan:
[List your plan for tomorrow]

CISO Input Needed:
[List any questions or input needed from the CISO]"""
    
    await ctx.send(reminder_msg)
    await ctx.send("📝 Journal submission reminder sent!")
    """Test user lookup by Discord ID"""
    if not user_id:
        await ctx.send("Please provide a Discord User ID to test. Usage: `!test_user 123456789`")
        return
    
    try:
        user_id_int = int(user_id)
        user = bot.get_user(user_id_int)
        
        if not user:
            user = await bot.fetch_user(user_id_int)
        
        if user:
            await ctx.send(f"✅ **User Found!**\n**Name:** {user.name}\n**Display Name:** {user.display_name}\n**ID:** {user.id}")
        else:
            await ctx.send(f"❌ User with ID {user_id} not found")
            
    except ValueError:
        await ctx.send(f"❌ Invalid user ID format: {user_id}")
    except discord.NotFound:
        await ctx.send(f"❌ User with ID {user_id} not found")
    except Exception as e:
        await ctx.send(f"❌ Error looking up user: {e}")

@bot.command(name='test')
async def test_bot(ctx):
    """Test command to verify bot is working"""
    await ctx.send("Elliot Alderson (CISO Bot) is online and monitoring! ✅\n*Ready to process journals with Discord User ID tracking and send CISO responses.*")

@bot.command(name='format')
async def format_command(ctx):
    """Show help message with journal format"""
    help_msg = f"""
**Elliot Alderson - CISO Bot Help** 📚

**How to Submit Your Journal:**
You can send your daily journal update in two ways:
1. **Direct Message** - Send me a private message with your update
2. **Channel** - Post in the designated channel (if configured)

**Required Format:**
```
Daily CISO Update - [Date]
Student: [Your Name]
Hours Worked: [Number]
Completed Today:
- [List your completed tasks]

Current Findings/Issues:
- [Any technical findings or blockers]

Tomorrow's Plan:
- [Your objectives for tomorrow]

CISO Input Needed:
- [Questions or guidance you need]
```

**New Feature: Discord ID Tracking** 🆔
Your Discord User ID is now automatically stored for reliable message delivery!

**Bot Reactions:**
✅ - Successfully processed and saved to database
❌ - Error occurred while saving
⚠️ - Format issue detected, please check your formatting

**Commands:**
- `!test` - Test if bot is responding
- `!test_user [user_id]` - Test Discord user lookup
- `!send_responses [admin_code] [date]` - Send pending CISO responses (ADMIN ONLY)
- `!preview_responses [admin_code] [date]` - Preview pending responses (ADMIN ONLY)
- `!response_count [admin_code] [date]` - Check response count (ADMIN ONLY)
- `!send_reminder` - Send journal submission reminder
- `!help` - Show this help message

**Example Journal Entry:**
```
Daily CISO Update - 2025-06-12
Student: John Smith
Hours Worked: 8
Completed Today:
- Configured firewall rules for DMZ
- Analyzed network traffic logs
- Completed SIEM dashboard setup

Current Findings/Issues:
- Detected unusual port scanning activity
- Need clarification on incident response procedures

Tomorrow's Plan:
- Investigate port scanning source
- Update security policies documentation
- Begin penetration testing phase

CISO Input Needed:
- Should we block the suspicious IP immediately?
- What's the escalation process for security incidents?
```

Happy journaling with improved reliability! 🛡️

*- Elliot Alderson, CISO Bot Assistant*
    """
    await ctx.send(help_msg)

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return  # Ignore unknown commands
    print(f'Error: {error}')

if __name__ == '__main__':
    # Verify required environment variables
    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_TOKEN environment variable not set")
        exit(1)
    if not NOTION_TOKEN:
        print("ERROR: NOTION_TOKEN environment variable not set")
        exit(1)
    if not NOTION_DATABASE_ID:
        print("ERROR: NOTION_DATABASE_ID environment variable not set")
        exit(1)
    if not ADMIN_CODE:
        print("WARNING: ADMIN_CODE environment variable not set - admin commands will be disabled")
    
    print("🚀 Starting Enhanced CISO Bot with Discord User ID tracking...")
    print(f"🔐 Admin protection: {'ENABLED' if ADMIN_CODE else 'DISABLED'}")
    
    # Start the bot
    bot.run(DISCORD_TOKEN)
