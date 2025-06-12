import discord
import re
import requests
import json
import os
from datetime import datetime, timedelta
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Environment variables
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
NOTION_DATABASE_ID = os.getenv('NOTION_DATABASE_ID')
CHANNEL_ID = int(os.getenv('CHANNEL_ID')) if os.getenv('CHANNEL_ID') else None
CISO_NAME = os.getenv('CISO_NAME', 'Your CISO')  # Your actual name

# Notion API headers
NOTION_HEADERS = {
    'Authorization': f'Bearer {NOTION_TOKEN}',
    'Content-Type': 'application/json',
    'Notion-Version': '2022-06-28'
}

def parse_ciso_update(message_content):
    """Parse the structured CISO update message"""
    try:
        # Extract date
        date_pattern = r'Daily CISO Update - (.+?)(?:\n|$)'
        date_match = re.search(date_pattern, message_content, re.IGNORECASE)
        date_str = date_match.group(1).strip() if date_match else datetime.now().strftime('%Y-%m-%d')
        
        # Extract student name
        student_pattern = r'Student:\s*(.+?)(?:\n|$)'
        student_match = re.search(student_pattern, message_content, re.IGNORECASE)
        student_name = student_match.group(1).strip() if student_match else "Unknown"
        
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
        ciso_pattern = r'CISO Input Needed:\s*(.*?)$'
        ciso_match = re.search(ciso_pattern, message_content, re.DOTALL | re.IGNORECASE)
        ciso_input = ciso_match.group(1).strip() if ciso_match else ""
        
        return {
            'date': date_str,
            'student_name': student_name,
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
            parsed_date = datetime.strptime(parsed_data['date'], '%Y-%m-%d').isoformat()
        except:
            # Try different date formats
            try:
                parsed_date = datetime.strptime(parsed_data['date'], '%m/%d/%Y').isoformat()
            except:
                parsed_date = datetime.now().isoformat()
        
        # Notion database entry structure
        data = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": {
                "Date": {
                    "date": {"start": parsed_date.split('T')[0]}
                },
                "Student Name": {
                    "title": [{"text": {"content": parsed_data['student_name']}}]
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
            target_date = datetime.now().strftime('%Y-%m-%d')
        
        # Query Notion database for entries with responses
        query_data = {
            "filter": {
                "and": [
                    {
                        "property": "Date",
                        "date": {
                            "equals": target_date
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
            return response.json()['results']
        else:
            print(f"Error fetching entries: {response.status_code} - {response.text}")
            return []
            
    except Exception as e:
        print(f"Error fetching entries with responses: {e}")
        return []

def extract_response_data(notion_entry):
    """Extract relevant data from Notion entry"""
    try:
        properties = notion_entry['properties']
        
        # Extract student name
        student_name = ""
        if 'Student Name' in properties and properties['Student Name']['title']:
            student_name = properties['Student Name']['title'][0]['text']['content']
        
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
            'date': entry_date,
            'ciso_response': ciso_response
        }
        
    except Exception as e:
        print(f"Error extracting response data: {e}")
        return None

def mark_response_sent(entry_id):
    """Mark a Notion entry as response sent"""
    try:
        update_data = {
            "properties": {
                "Response Sent": {
                    "checkbox": True
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

async def send_ciso_response(student_name, date, response_text):
    """Send CISO response to student via DM"""
    try:
        # Find the user by name (this is a simplified approach)
        # In production, you might want to store Discord user IDs in Notion
        user = None
        for guild in bot.guilds:
            for member in guild.members:
                if member.display_name.lower() == student_name.lower() or member.name.lower() == student_name.lower():
                    user = member
                    break
            if user:
                break
        
        if not user:
            print(f"Could not find Discord user for: {student_name}")
            return False
        
        # Format the message
        message = f"""🛡️ **Message from your CISO - {CISO_NAME}**
*Delivered via Elliot Alderson Bot*

Hi {student_name},

I've reviewed your journal entry from {date}. Here's my personal feedback:

{response_text}

Remember, I'm always here to support your cybersecurity journey. Feel free to reach out directly if you need immediate assistance.

Best regards,
{CISO_NAME}
Your CISO

---
*This message was delivered through Elliot Alderson, your CISO Bot Assistant*"""
        
        # Send DM
        await user.send(message)
        return True
        
    except discord.Forbidden:
        print(f"Cannot send DM to {student_name} - DMs might be disabled")
        return False
    except Exception as e:
        print(f"Error sending response to {student_name}: {e}")
        return False
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Monitoring channel ID: {CHANNEL_ID}')

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return
    
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
        print(f"CISO update detected from {message.author.name} via {message_type}")
        
        # Parse the message
        parsed_data = parse_ciso_update(message.content)
        
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
**Date:** {parsed_data['date']}
**Hours:** {parsed_data['hours_worked']}

Your journal entry has been recorded in the database. I'll review it and may send you personalized feedback later today.

Keep up the excellent work on your cybersecurity journey! 🎯

*- Elliot Alderson, CISO Bot Assistant*
                    """
                    await message.channel.send(confirmation_msg)
                
                print(f"Successfully processed update for {parsed_data['student_name']} via {message_type}")
                
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
async def send_daily_responses(ctx, date=None):
    """Send all pending CISO responses for a specific date"""
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    await ctx.send(f"🔍 Checking for pending CISO responses for {date}...")
    
    # Get entries with responses
    entries = get_entries_with_responses(date)
    
    if not entries:
        await ctx.send(f"📭 No pending responses found for {date}")
        return
    
    sent_count = 0
    failed_count = 0
    
    for entry in entries:
        response_data = extract_response_data(entry)
        if not response_data:
            failed_count += 1
            continue
        
        # Send the response
        success = await send_ciso_response(
            response_data['student_name'],
            response_data['date'],
            response_data['ciso_response']
        )
        
        if success:
            # Mark as sent in Notion
            if mark_response_sent(response_data['entry_id']):
                sent_count += 1
                print(f"✅ Response sent to {response_data['student_name']}")
            else:
                failed_count += 1
                print(f"❌ Failed to mark response as sent for {response_data['student_name']}")
        else:
            failed_count += 1
    
    # Send summary
    summary = f"""📊 **Response Sending Complete**

✅ **Successfully sent:** {sent_count} responses
❌ **Failed:** {failed_count} responses
📅 **Date:** {date}

All students have received their personalized feedback from {CISO_NAME}!"""
    
    await ctx.send(summary)

@bot.command(name='preview_responses')
async def preview_responses(ctx, date=None):
    """Preview what responses will be sent without actually sending them"""
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    entries = get_entries_with_responses(date)
    
    if not entries:
        await ctx.send(f"📭 No pending responses found for {date}")
        return
    
    preview_msg = f"📋 **Response Preview for {date}**\n\n"
    
    for i, entry in enumerate(entries, 1):
        response_data = extract_response_data(entry)
        if response_data:
            preview_msg += f"**{i}. {response_data['student_name']}**\n"
            preview_msg += f"Response: {response_data['ciso_response'][:100]}{'...' if len(response_data['ciso_response']) > 100 else ''}\n\n"
    
    # Discord has message length limits, so split if needed
    if len(preview_msg) > 2000:
        preview_msg = preview_msg[:1900] + "\n\n*... (truncated for length)*"
    
    await ctx.send(preview_msg)
    await ctx.send(f"📬 Ready to send {len(entries)} responses. Use `!send_responses` to send them.")

@bot.command(name='response_count')
async def response_count(ctx, date=None):
    """Show count of pending responses"""
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    entries = get_entries_with_responses(date)
    count = len(entries)
    
    if count == 0:
        await ctx.send(f"📭 No pending responses for {date}")
    else:
        await ctx.send(f"📬 **{count}** pending responses ready to send for {date}")

# Commented out automatic daily sending - uncomment and configure if needed
# @tasks.loop(time=datetime.time(18, 0))  # 6 PM daily
# async def daily_response_sender():
#     """Automatically send responses daily at 6 PM"""
#     date = datetime.now().strftime('%Y-%m-%d')
#     entries = get_entries_with_responses(date)
#     
#     if not entries:
#         return
#     
#     sent_count = 0
#     for entry in entries:
#         response_data = extract_response_data(entry)
#         if response_data:
#             success = await send_ciso_response(
#                 response_data['student_name'],
#                 response_data['date'],
#                 response_data['ciso_response']
#             )
#             if success and mark_response_sent(response_data['entry_id']):
#                 sent_count += 1
#     
#     print(f"Daily auto-send complete: {sent_count} responses sent")

@bot.command(name='test')
async def test_bot(ctx):
    """Test command to verify bot is working"""
    await ctx.send("Elliot Alderson (CISO Bot) is online and monitoring! ✅\n*Ready to process journals and send CISO responses.*")

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

**Bot Reactions:**
✅ - Successfully processed and saved to database
❌ - Error occurred while saving
⚠️ - Format issue detected, please check your formatting

**Commands:**
- `!test` - Test if bot is responding
- `!status` - Show bot configuration status
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

Happy journaling! 🛡️

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
    
    # Start the bot
    bot.run(DISCORD_TOKEN)
