# League of Legends Discord Bot

A Discord bot that automatically tracks League of Legends matches for multiple summoners and posts detailed match results. Features modern slash commands, rich embeds, and comprehensive player statistics.

## ✨ Features

- **🔄 Automatic Match Tracking**: Monitors multiple summoners and posts results to Discord
- **⚡ Slash Commands**: Modern Discord UI with 11 interactive commands
- **🎨 Rich Embeds**: Beautiful embeds with champion icons, ANSI colors, and stats
- **👥 Multi-Summoner Support**: Track unlimited players simultaneously
- **🔔 Ping Notifications**: Get pinged when specific players finish games
- **📊 Comprehensive Stats**: Ranked, KDA, history, mastery, and live game info

## 📋 Commands

### Player Statistics
- `/rank [riot_id]` - Show Solo/Duo and Flex ranked stats
- `/history [riot_id]` - Last 10 games with KDA, CS, game mode, and champion icons
- `/kda <champion> [riot_id] [count]` - Champion-specific performance analysis
- `/mastery [riot_id] [champion]` - Champion mastery levels and points
- `/livegame [riot_id]` - Current game details (if playing)

### Summoner Management
- `/addsummoner <game_name> <tag_line> [ping]` - Add summoner to tracking (optional Discord ping)
- `/listsummoners` - View all tracked summoners
- `/addmulti <opgg_url>` - Bulk add from OP.GG multi-search URL
- `/delsummoner <riot_id>` - Remove summoner (Admin only)
- `/cleanup` - Remove invalid/inactive summoners (Admin only)

### Help
- `/help [command]` - Command documentation and examples

## 🚀 Quick Start for Your Server

### For Server Admins

**1. Invite the Bot**

Use this URL (replace `YOUR_CLIENT_ID` with the bot's Application ID from Discord Developer Portal):
```
https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&scope=bot%20applications.commands&permissions=274877959168
```

**2. Configure the Channel**

Run `/addsummoner` in the channel where you want match notifications.

**3. Add Summoners**

```
/addsummoner Faker T1
/addsummoner Doublelift NA1 <@YOUR_USER_ID>
```

The bot will automatically track their games and post results every 5 minutes!

---

## 🛠️ Setup (For Hosting Your Own Instance)

### Prerequisites

- **Python 3.10+**
- **Discord Bot Token** - [Get one here](https://discord.com/developers/applications)
- **Riot API Key** - [Get one here](https://developer.riotgames.com/)

### Installation

**1. Clone & Install**

```bash
git clone https://github.com/yourusername/DiscordPythonBot.git
cd DiscordPythonBot
pip install -r requirements.txt
```

**2. Create Configuration File**

Create a `.env` file in the root directory:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token_here
RIOT_API_KEY=your_riot_api_key_here
CHANNEL_ID=your_discord_channel_id_here
```

**3. Get Your Credentials**

<details>
<summary><b>🤖 Discord Bot Token</b></summary>

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to the "Bot" tab → Click "Add Bot"
4. Under "Token", click "Reset Token" and copy it
5. **Enable these Privileged Intents:**
   - ✅ Message Content Intent
   - ✅ Server Members Intent (optional)
6. Save your token to `.env`

**Bot Invite URL:**
```
https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&scope=bot%20applications.commands&permissions=274877959168
```
Replace `YOUR_CLIENT_ID` with the Application ID from the "General Information" tab.

</details>

<details>
<summary><b>🎮 Riot API Key</b></summary>

1. Visit [Riot Developer Portal](https://developer.riotgames.com/)
2. Sign in with your Riot Games account
3. Copy your **Development API Key** (expires every 24 hours)
   - For production: Apply for a **Production API Key** (permanent)
4. Save to `.env`

⚠️ **Note**: Development keys expire daily. For 24/7 operation, apply for production access.

</details>

<details>
<summary><b>💬 Discord Channel ID</b></summary>

1. Enable Developer Mode in Discord:
   - Settings → Advanced → Developer Mode (toggle ON)
2. Right-click the channel where you want match notifications
3. Click "Copy Channel ID"
4. Save to `.env`

</details>


**4. Run the Bot**

```bash
python Working.py
```

The bot will:
- ✅ Connect to Discord and sync slash commands
- ✅ Load champion data from Riot's Data Dragon
- ✅ Start checking for new matches every 5 minutes
- ✅ Post match results automatically

---

## 📁 File Structure

```
DiscordPythonBot/
├── Working.py              # Main bot code (2,288 lines)
├── requirements.txt        # Python dependencies
├── .env                   # Your credentials (DO NOT COMMIT)
├── .env.example           # Template for others
├── .gitignore            # Protects .env from being uploaded
├── summoners.json        # Tracked players (auto-created)
├── last_matches.json     # Match state (auto-created)
└── README.md             # Documentation
```

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `DISCORD_BOT_TOKEN` | ✅ Yes | Discord bot token from Developer Portal | `MTQzNz...` |
| `RIOT_API_KEY` | ✅ Yes | Riot API key (dev or production) | `RGAPI-...` |
| `CHANNEL_ID` | ✅ Yes | Channel ID for match notifications | `1437933626...` |

### Region Settings (Optional)

Default: **North America**. To change regions, edit `Working.py` (lines 61-62):

```python
REGION = "na1"           # Platform: na1, euw1, kr, br1, etc.
ROUTING_REGION = "americas"  # Routing: americas, europe, asia, sea
```

**Region Reference:**
- **Americas**: na1, br1, la1, la2
- **Europe**: euw1, eune1, tr1, ru
- **Asia**: kr, jp1
- **SEA**: oc1, ph2, sg2, th2, tw2, vn2

## 📊 Data Files (Auto-Generated)

### `summoners.json`
Stores tracked summoners with metadata:
```json
{
  "GameName#TAG": {
    "puuid": "...",
    "summoner_id": "...",
    "added_at": "2025-11-20T10:00:00",
    "ping_id": "<@291714837669478410>"  // Optional
  }
}
```

### `last_matches.json`
Prevents duplicate match posts:
```json
{
  "puuid_here": "NA1_1234567890"
}
```

## 🔧 Troubleshooting

<details>
<summary><b>❌ Slash commands don't appear</b></summary>

**Solutions:**
1. Wait 1-2 minutes after bot starts (global sync takes time)
2. Kick and re-invite the bot with the correct invite URL
3. Check bot has "Use Application Commands" permission
4. Restart Discord client

**Verify in console:**
```
✓ Globally synced 11 slash command(s): rank, history, kda, ...
```

</details>

<details>
<summary><b>⚠️ "Rate limited" errors</b></summary>

**Development API Key Limits:**
- 20 requests/second
- 100 requests/2 minutes

**Solutions:**
- Bot has built-in rate limiting (10 concurrent requests max)
- Apply for Production Key for 24/7 operation
- Reduce number of tracked summoners

</details>

<details>
<summary><b>🔴 Match tracking not working</b></summary>

**Checklist:**
1. ✅ Bot is running (`python Working.py`)
2. ✅ Summoners added correctly (`/listsummoners`)
3. ✅ Bot has "Send Messages" permission in notification channel
4. ✅ Check console for errors
5. ✅ Player has played a game in last 5 minutes

**Test immediately:**
```python
# In Working.py, change check interval from 5 minutes to 1 minute:
@tasks.loop(minutes=1)  # Changed from minutes=5
```

</details>

<details>
<summary><b>🎮 Riot API key expired</b></summary>

**Development keys expire every 24 hours.**

**Quick fix:**
1. Go to [Riot Developer Portal](https://developer.riotgames.com/)
2. Copy new Development API Key
3. Update `.env` file
4. Restart bot

**Permanent solution:** Apply for Production API Key (doesn't expire)

</details>

## 🎨 Customization

### Ping Notifications

Add summoners with custom pings:
```
/addsummoner Faker T1 <@123456789>
```

When Faker finishes a game, `@user` gets pinged!

### Match Check Frequency

Edit `Working.py` line ~1385:
```python
@tasks.loop(minutes=5)  # Change to desired interval
async def check_for_new_matches():
```

⚠️ Lower intervals = more API requests = higher rate limit risk

### Admin-Only Commands

By default, `/cleanup` and `/delsummoner` require Discord Administrator permission.

To change, remove `@app_commands.default_permissions(administrator=True)` decorators.

## 🚀 Deployment (24/7 Hosting)

### Option 1: Cloud VPS (Recommended)
- **DigitalOcean**: $6/month droplet
- **AWS EC2**: Free tier eligible
- **Google Cloud**: $10/month credit

**Setup:**
```bash
# Clone repo
git clone https://github.com/yourusername/DiscordPythonBot.git
cd DiscordPythonBot

# Install dependencies
pip install -r requirements.txt

# Configure .env
nano .env

# Run with screen/tmux
screen -S lolbot
python Working.py
# Press Ctrl+A then D to detach
```

### Option 2: Replit / Railway / Render
- Free tier available on most platforms
- Use "Always On" feature (may require paid plan)
- Add `.env` variables in platform's secrets manager

### Option 3: Local PC (24/7)
- Simple but requires always-on computer
- Use Task Scheduler (Windows) or cron (Linux) for auto-restart

## 📝 License

MIT License - feel free to modify and distribute!

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Test thoroughly
4. Submit a pull request

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/DiscordPythonBot/issues)
- **Discord**: Your Discord server invite
- **Riot API Docs**: https://developer.riotgames.com/apis

---

**Made with ❤️ for the League of Legends community**

## License

MIT License - feel free to modify and use for your own projects.

## Credits

- Built with [discord.py](https://github.com/Rapptz/discord.py)
- Uses [Riot Games API](https://developer.riotgames.com/)
- Champion data from [Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon)

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review Discord and Riot API documentation
3. Check console logs for detailed error messages
