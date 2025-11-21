# League of Legends Discord Bot

A Discord bot that automatically tracks League of Legends matches for multiple summoners and posts detailed match results. Features modern slash commands, rich embeds, and comprehensive player statistics.

## ✨ Features

- 🔍 **Automatic Match Tracking**: Monitors multiple summoners and posts results to Discord
- ⚡ **Slash Commands**: Modern Discord UI with 10+ interactive commands
- 🎨 **Rich Embeds**: Beautiful embeds with champion icons, colors, and stats
- 👥 **Multi-Summoner Support**: Track unlimited players simultaneously
- 🔔 **Ping Notifications**: Get pinged when specific players finish games
- 📊 **Comprehensive Stats**: Ranked, KDA, history, mastery info

## 📋 Commands

### 📈 Player Statistics
- `/rank [summoner]` - Show Solo/Duo and Flex ranked stats
- `/history [summoner]` - Last 10 games with KDA, CS, game mode, and champion icons
- `/kda <champion> [summoner] [count]` - Champion-specific performance analysis
- `/mastery [summoner] [champion]` - Champion mastery levels and points

### 👤 Summoner Management
- `/addsummoner <riot_id> <ping_choice> [user_ping]` - Add summoner to tracking
- `/listsummoners` - View all tracked summoners
- `/addmulti <opgg_url>` - Bulk add from OP.GG multi-search URL
- `/delsummoner [summoner]` - Remove summoner (Admin only)
- `/cleanup` - Clear matches file (Admin only)
- `/help` - Command documentation

## 🚀 Quick Start for Your Server

### For Server Admins

**1. Invite the Bot**

Use this URL (replace `YOUR_CLIENT_ID` with the bot's Application ID):
```
https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&scope=bot%20applications.commands&permissions=274877959168
```

**2. Configure & Add Summoners**

```
/addsummoner Faker#T1 yes
/addsummoner Doublelift#NA1 yes @your_username
```

The bot automatically tracks games every 5 minutes!

---

## ⚙️ Setup (For Hosting Your Own Instance)

### Prerequisites

- **Python 3.10+**
- **Discord Bot Token** - [Get one here](https://discord.com/developers/applications)
- **Riot API Key** - [Get one here](https://developer.riotgames.com/)

### Installation

**1. Clone & Install**

```bash
git clone https://github.com/Spritemelody/Melodys-LoL-Tracker.git
cd Melodys-LoL-Tracker
pip install -r requirements.txt
```

**2. Create Configuration File**

Create a `.env` file in the root directory:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token_here
RIOT_API_KEY=your_riot_api_key_here
CHANNEL_ID=your_discord_channel_id_here
VOD_CHANNEL_ID=your_vod_channel_id_here
```

**3. Get Your Discord Bot Token**

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to the "Bot" tab and click "Add Bot"
4. Under "Token", click "Copy" to copy your token
5. Enable these Privileged Intents:
   - Message Content Intent
   - Server Members Intent
6. Save your token to `.env`

**4. Get Your Riot API Key**

1. Go to [Riot Developer Portal](https://developer.riotgames.com/)
2. Sign in with your Riot account
3. Generate a personal API key (valid for 24 hours)
4. Save it to `.env` as `RIOT_API_KEY`

**5. Get Your Discord Channel IDs**

1. Enable Developer Mode in Discord (User Settings > Advanced > Developer Mode)
2. Right-click any channel and select "Copy Channel ID"
3. Save to `.env` as `CHANNEL_ID` (for match notifications)
4. Optionally set `VOD_CHANNEL_ID` (for replay videos)

**6. Run the Bot**

```bash
python Working.py
```

You should see:
```
League of Legends Match Tracker Bot
Logged in as: Melodys LOL Tracker
Target Channel ID: YOUR_CHANNEL_ID
```

---

## 📁 File Structure

```
DiscordPythonBot/
├── Working.py              # Main bot code (2,288 lines)
├── requirements.txt        # Python dependencies
├── .env                    # Your credentials (protected by .gitignore - safe!)
├── .env.example            # Template for others
├── .gitignore              # Keeps .env safe & local
├── summoners.json          # Tracked players (auto-created)
├── last_matches.json       # Match state (auto-created)
└── README.md               # Documentation
```

---

## ⚙️ How It Works

### Match Detection Loop
- Runs every 5 minutes
- Checks all tracked summoners for new matches
- Compares current match ID with last stored ID
- Posts new matches automatically

### Match Embeds Include
- Champion name and icon
- KDA (Kills/Deaths/Assists)
- CS (Creep Score) and CS/min
- Game duration
- Game mode
- LP gained/lost (for ranked)
- Match timestamp

### Ranked Stats
Shows your current rank for:
- Solo/Duo Queue
- Flexible Queue
- Wins, losses, and LP

### Mastery Info
Displays champion masteries with:
- Mastery level (1-7)
- Mastery points
- Star ratings

---

## 🔧 Configuration

### Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `DISCORD_BOT_TOKEN` | Yes | Discord bot authentication token | `MTA4NzI4MTY5Nz...` |
| `RIOT_API_KEY` | Yes | Riot API key for League data | `RGAPI-...` |
| `CHANNEL_ID` | Yes | Channel ID for match notifications | `1437933626850283651` |
| `VOD_CHANNEL_ID` | No | Channel ID for replay videos | `1441107047704821772` |

### Default Settings

- **Default Summoner**: Blinds2Blinkers#Pyke
- **Check Interval**: 5 minutes
- **Region**: NA1 (North America)
- **Queue Types**: Ranked Solo, Ranked Flex, Draft, Blind, ARAM

---

## 🔍 Troubleshooting

### Bot doesn't start
- Check that all environment variables are set correctly in `.env`
- Verify your Discord bot token is valid
- Make sure your Riot API key hasn't expired (personal keys expire every 24 hours)

### Bot doesn't post matches
- Verify the channel ID is correct
- Make sure the bot has "Send Messages" and "Embed Links" permissions
- Check that summoner names are spelled correctly (case-sensitive)

### Bot says summoner not found
- Verify the Riot ID format: `GameName#TagLine`
- Check the summoner exists on OP.GG
- Ensure you're using the correct region (NA1 for North America)

---

## 💻 Development

### Key Functions

- `get_puuid_from_riot_id_v2()` - Fetch summoner PUUID from Riot ID
- `get_match_history()` - Retrieve recent matches
- `get_match_details()` - Get full match data
- `post_match_to_discord()` - Format and send embeds
- `check_for_new_matches()` - Main polling loop

### Adding New Commands

1. Use `@app_commands.command()` decorator
2. Implement command handler function
3. Add to bot's command list
4. Add help text in `/help` command

---

## 📜 License

This project is for personal use. Feel free to fork and modify!

## 💬 Support

For issues or questions:
- Open a GitHub issue
- Check the existing documentation
- Contact me on Discord: **@Spritemelody**
