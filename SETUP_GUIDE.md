# 🚀 Quick Setup Guide for League of Legends Discord Bot

This guide will get your bot running in **5 minutes**!

## 📋 Checklist

Before starting, you'll need:
- [ ] Python 3.10 or newer installed
- [ ] A Discord account (with permissions to add bots to your server)
- [ ] A Riot Games account (for API access)

---

## Step 1: Download the Bot

```bash
# Clone the repository
git clone https://github.com/yourusername/DiscordPythonBot.git
cd DiscordPythonBot

# Install required packages
pip install -r requirements.txt
```

**Or download the ZIP:**
1. Click the green "Code" button on GitHub
2. Select "Download ZIP"
3. Extract to a folder
4. Open terminal/command prompt in that folder
5. Run: `pip install -r requirements.txt`

---

## Step 2: Create Discord Bot

### 2a. Create Application
1. Go to https://discord.com/developers/applications
2. Click **"New Application"**
3. Name it (e.g., "LoL Match Tracker")
4. Click **"Create"**

### 2b. Create Bot User
1. Click **"Bot"** in the left sidebar
2. Click **"Add Bot"** → Confirm
3. Click **"Reset Token"** → Copy and save this token ⚠️
4. Scroll down to **"Privileged Gateway Intents"**:
   - ✅ Enable **Message Content Intent**
5. Click **"Save Changes"**

### 2c. Invite Bot to Your Server
1. Click **"OAuth2"** → **"URL Generator"** in left sidebar
2. Under **SCOPES**, check:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Under **BOT PERMISSIONS**, check:
   - ✅ Send Messages
   - ✅ Embed Links
   - ✅ Attach Files
   - ✅ Read Message History
   - ✅ Use Application Commands
4. Copy the **Generated URL** at the bottom
5. Open URL in browser → Select your server → **Authorize**

---

## Step 3: Get Riot API Key

1. Go to https://developer.riotgames.com/
2. Sign in with your Riot account
3. Choose your API key type:
   - **Personal API Key** (Recommended): Doesn't expire, perfect for personal use
   - **Development API Key**: Expires every 24 hours, need to regenerate daily
   - **Production API Key**: Apply for approval, for public bots
4. Copy the key

---

## Step 4: Configure the Bot

### 4a. Get Discord Channel ID
1. Open Discord
2. Enable Developer Mode: **User Settings** → **Advanced** → Toggle **Developer Mode** ON
3. Right-click the channel where you want match updates
4. Click **"Copy Channel ID"**

### 4b. Create `.env` File
1. In the bot folder, copy `.env.example` to `.env`:
   ```bash
   # On Windows:
   copy .env.example .env
   
   # On Mac/Linux:
   cp .env.example .env
   ```

2. Open `.env` in a text editor (Notepad, VS Code, etc.)

3. Fill in your credentials:
   ```env
   DISCORD_BOT_TOKEN=MTQzNzkyNzE2Mjc5NDQ3OTY0Nw.GLk-Un.WO3yaYC... (paste your bot token)
   RIOT_API_KEY=RGAPI-9aa2e33c-f81c-43ed-9bd6-fbc4177b8e02 (paste your Riot key)
   CHANNEL_ID=1437933626850283651 (paste your channel ID)
   ```

4. Save the file

---

## Step 5: Run the Bot! 🎉

```bash
python Working.py
```

**You should see:**
```
2025-11-20 10:00:00,123 INFO: ✓ Logged in as YourBotName#1234
2025-11-20 10:00:02,456 INFO: ✓ Globally synced 11 slash command(s): rank, history, kda, ...
2025-11-20 10:00:03,789 INFO: Checking for new matches for 0 summoners...
```

✅ **Success!** The bot is now online in your Discord server.

---

## Step 6: Add Summoners to Track

In your Discord server, use the slash commands:

```
/addsummoner Faker T1
/addsummoner Doublelift NA1
/addsummoner YourGameName YourTag <@YourDiscordID>
```

The last one will ping you when that player finishes a game!

**Verify they were added:**
```
/listsummoners
```

---

## 🎮 Test the Bot

Try these commands to verify everything works:

```
/rank Faker#T1
/history Doublelift#NA1
/kda Jinx
/mastery Faker#T1
```

---

## ⚙️ Customization

### Change Match Check Frequency
Default is every 5 minutes. To change:

1. Open `Working.py`
2. Find line ~1385: `@tasks.loop(minutes=5)`
3. Change to your preference (e.g., `minutes=1` for faster updates)
4. ⚠️ Lower values = more API requests

### Change Region
Default is North America. To change:

1. Open `Working.py`
2. Find lines ~61-62:
   ```python
   REGION = "na1"  # Change to: euw1, kr, br1, etc.
   ROUTING_REGION = "americas"  # Change to: europe, asia, sea
   ```
3. Restart bot

---

## 🆘 Common Issues

### "Bot doesn't respond to slash commands"
- Wait 1-2 minutes after starting the bot
- Make sure bot has "Use Application Commands" permission
- Try kicking and re-inviting the bot

### "401 Unauthorized" errors
- Your Riot API key expired (dev keys expire every 24 hours)
- Get a new key from https://developer.riotgames.com/
- Update `.env` and restart bot

### "Match tracking not working"
- Check console for errors
- Verify summoners are added: `/listsummoners`
- Make sure bot can send messages in the notification channel
- Player must finish a game for it to post

### "Bot goes offline"
- Development API keys expire daily
- Your computer/server turned off
- Consider hosting on a VPS for 24/7 operation

---

## 🚀 Next Steps

### For 24/7 Operation:
1. **Get Production API Key**: Apply at https://developer.riotgames.com/
2. **Host on VPS**: DigitalOcean ($6/mo), AWS, Google Cloud
3. **Use Process Manager**: `screen`, `tmux`, or `pm2`

### Deployment Example (Ubuntu VPS):
```bash
# Install Python
sudo apt update
sudo apt install python3 python3-pip git

# Clone and setup
git clone https://github.com/yourusername/DiscordPythonBot.git
cd DiscordPythonBot
pip3 install -r requirements.txt

# Configure .env
nano .env
# (paste your credentials)

# Run with screen (persists after logout)
screen -S lolbot
python3 Working.py
# Press Ctrl+A then D to detach
```

---

## 📚 Full Documentation

See `README.md` for:
- Complete command reference
- Advanced configuration
- Troubleshooting details
- Development guide

---

**Need help?** Open an issue on GitHub or ask in the Discord community!

✨ **Enjoy your League of Legends bot!** ✨
