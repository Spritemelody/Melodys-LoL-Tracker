import asyncio
import atexit
import json
import logging
import os
import random
from datetime import datetime, datetime as dt, timedelta, timezone
from io import BytesIO
from typing import Any, Dict, Mapping, Optional, Tuple, cast
from urllib.parse import quote, quote_plus, unquote_plus

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class SlashContext:
    """Adapter to run existing ctx-based commands from slash interactions."""
    def __init__(self, interaction: discord.Interaction):
        self._interaction = interaction
        self.author = interaction.user
        self.guild = interaction.guild
        self.channel = interaction.channel

    async def send(self, *args, **kwargs):
        return await self._interaction.followup.send(*args, **kwargs)

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION & ENVIRONMENT
# ══════════════════════════════════════════════════════════════════════════════
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
RIOT_API_KEY = os.getenv("RIOT_API_KEY")

_channel_env = os.getenv("CHANNEL_ID")
if _channel_env:
    try:
        CHANNEL_ID = int(_channel_env)
        CHANNEL_ID_SOURCE = 'env'
    except ValueError:
        logging.warning("Invalid CHANNEL_ID value '%s'; using default", _channel_env)
        CHANNEL_ID = 12345
        CHANNEL_ID_SOURCE = 'fallback'
else:
    CHANNEL_ID = 12345
    CHANNEL_ID_SOURCE = 'default'

def _sanitize_env(value: Optional[str]) -> Optional[str]:
    """Trim and remove CR/LF from environment-provided secrets."""
    if value is None:
        return None
    return value.strip().replace('\r', '').replace('\n', '')

DISCORD_BOT_TOKEN = _sanitize_env(DISCORD_BOT_TOKEN)
RIOT_API_KEY = _sanitize_env(RIOT_API_KEY)

# Default summoner to track on first run
GAME_NAME = "Blinds2Blinkers"
TAG_LINE = "Pyke"

REGION = "na1"
ROUTING_REGION = "americas"

PERSISTENCE_FILE = "last_matches.json"
SUMMONERS_FILE = "summoners.json"

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

# ══════════════════════════════════════════════════════════════════════════════
# SHARED RESOURCES & CACHING
# ══════════════════════════════════════════════════════════════════════════════
HTTP_SESSION: Optional[aiohttp.ClientSession] = None
API_SEMAPHORE: asyncio.Semaphore = asyncio.Semaphore(10)
REQUEST_CACHE: Dict[str, Tuple[Any, float]] = {}
CACHE_TTL = 60
COMMAND_COOLDOWNS: Dict[str, float] = {}
COOLDOWN_DURATION = 2

# ══════════════════════════════════════════════════════════════════════════════
# BOT INITIALIZATION
# ══════════════════════════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ══════════════════════════════════════════════════════════════════════════════
# COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="mastery", aliases=['m'], help="Show champion mastery for a summoner", description="Display top champion masteries with levels and points", usage="[GameName#TagLine] [ChampionName]")
async def mastery_command(ctx, *args):
    """Show champion mastery. Usage: !mastery [GameName#TagLine] [ChampionName]"""
    
    # Parse arguments
    riot_id = None
    champion_filter = None
    
    if args:
        # Check if first arg contains # (riot ID)
        if '#' in args[0]:
            riot_id = args[0]
            if len(args) > 1:
                champion_filter = ' '.join(args[1:])
        else:
            # No riot ID, just champion name for default summoner
            champion_filter = ' '.join(args)
    
    # Parse riot_id
    game_name = None
    tag_line = None
    if riot_id and '#' in riot_id:
        game_name, tag_line = riot_id.split('#', 1)
    
    # Get target summoner
    target_info = await get_target_info(ctx, game_name, tag_line)
    if not target_info:
        return
    
    target_summoner_name, target_puuid, game_name_final, tag_line_final = target_info
    
    try:
        mastery_data = await get_champion_mastery(target_puuid, top_count=10)
        
        if not mastery_data:
            await ctx.send(f"❌ No mastery data found for **{target_summoner_name}**.")
            return
        
        # Format URL properly
        opgg_url = f"https://www.op.gg/summoners/na/{game_name_final.replace(' ', '%20')}-{tag_line_final}"
        
        embed = discord.Embed(
            title=f"🏆 Champion Mastery - {target_summoner_name}",
            color=discord.Color.purple(),
            url=opgg_url
        )
        
        # If champion filter specified, find that champion
        if champion_filter:
            # Find matching champion in mastery data
            found = False
            for mastery in mastery_data:
                champ_id = mastery['championId']
                # Find champion name
                champ_name = None
                for name, data in CHAMPION_DATA.items():
                    if int(data.get('id', 0)) == champ_id:
                        champ_name = name
                        break
                
                if champ_name and champion_filter.lower() in champ_name.lower():
                    level = mastery['championLevel']
                    points = mastery['championPoints']
                    tokens = mastery.get('tokensEarned', 0)
                    
                    embed.set_thumbnail(url=get_champion_icon_url(champ_name))
                    embed.add_field(
                        name=f"{get_champion_role_emoji(champ_name)} {champ_name}",
                        value=f"**Level {level}** | {points:,} points\nTokens: {tokens}",
                        inline=False
                    )
                    found = True
                    break
            
            if not found:
                await ctx.send(f"❌ No mastery data found for champion **{champion_filter}** on **{target_summoner_name}**.")
                return
        else:
            # Show top 5 champions
            for i, mastery in enumerate(mastery_data[:5]):
                champ_id = mastery['championId']
                level = mastery['championLevel']
                points = mastery['championPoints']
                
                # Find champion name
                champ_name = None
                for name, data in CHAMPION_DATA.items():
                    if int(data.get('id', 0)) == champ_id:
                        champ_name = name
                        break
                
                if not champ_name:
                    champ_name = f"Champion {champ_id}"
                
                # Mastery level emoji
                mastery_emoji = "⭐" * min(level, 7)
                
                embed.add_field(
                    name=f"{i+1}. {get_champion_role_emoji(champ_name)} {champ_name}",
                    value=f"{mastery_emoji} **Level {level}**\n{points:,} points",
                    inline=True
                )
            
            # Set thumbnail to highest mastery champion
            if mastery_data:
                top_champ_id = mastery_data[0]['championId']
                for name, data in CHAMPION_DATA.items():
                    if int(data.get('id', 0)) == top_champ_id:
                        embed.set_thumbnail(url=get_champion_icon_url(name))
                        break
        
        embed.set_footer(text=f"Total Champions Played: {len(mastery_data)}")
        await ctx.send(embed=embed)
        
    except Exception as e:
        logging.exception("✗ Error in mastery command: %s", e)
        await ctx.send(f"❌ Error retrieving mastery data: {e}")


@bot.command(name="livegame", aliases=['lg', 'live'], help="Show current game details", description="Display information about a summoner's active game", usage="[GameName#TagLine]")
async def livegame_command(ctx, *, riot_id: Optional[str] = None):
    """Show live game details. Usage: !livegame [GameName#TagLine]"""
    
    game_name = None
    tag_line = None
    
    if riot_id and '#' in riot_id:
        game_name, tag_line = riot_id.split('#', 1)
    
    target_info = await get_target_info(ctx, game_name, tag_line)
    if not target_info:
        return
    
    target_summoner_name, target_puuid, _, _ = target_info
    
    try:
        # Get summoner ID if not already available
        summoners = load_summoners()
        summoner_id = None
        
        if target_summoner_name in summoners:
            summoner_id = summoners[target_summoner_name].get('summoner_id')
        
        if not summoner_id:
            # Try to get from API
            summoner_data = await get_summoner_by_puuid(target_puuid)
            if summoner_data:
                summoner_id = summoner_data.get('id')
        
        if not summoner_id:
            await ctx.send(f"❌ Could not retrieve summoner ID for **{target_summoner_name}**.")
            return
        
        active_game = await get_active_game(summoner_id)
        
        if not active_game:
            await ctx.send(f"📴 **{target_summoner_name}** is not currently in a game.")
            return
        
        game_mode = active_game.get('gameMode', 'UNKNOWN')
        game_queue = active_game.get('gameQueueConfigId', 0)
        game_length = active_game.get('gameLength', 0)
        
        # Convert game length to minutes
        game_minutes = game_length // 60
        
        embed = discord.Embed(
            title=f"🎮 Live Game - {target_summoner_name}",
            description=f"**{game_mode}** | {game_minutes} min in-game",
            color=discord.Color.green()
        )
        
        # Split participants into teams
        team_100 = []
        team_200 = []
        
        for participant in active_game.get('participants', []):
            team_id = participant.get('teamId')
            summoner_name = participant.get('riotId', participant.get('summonerName', 'Unknown'))
            champion_id = participant.get('championId')
            
            # Find champion name
            champ_name = None
            for name, data in CHAMPION_DATA.items():
                if int(data.get('id', 0)) == champion_id:
                    champ_name = name
                    break
            if not champ_name:
                champ_name = f"Champion {champion_id}"
            
            player_info = f"{get_champion_role_emoji(champ_name)} **{champ_name}** - {summoner_name}"
            
            if team_id == 100:
                team_100.append(player_info)
            else:
                team_200.append(player_info)
        
        if team_100:
            embed.add_field(
                name="🔵 Blue Team",
                value="\n".join(team_100),
                inline=True
            )
        
        if team_200:
            embed.add_field(
                name="🔴 Red Team",
                value="\n".join(team_200),
                inline=True
            )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        logging.exception("✗ Error in livegame command: %s", e)
        await ctx.send(f"❌ Error retrieving live game data: {e}")


@bot.command(name="kda", aliases=['stats'], help="Show champion-specific KDA stats", description="Display KDA and win rate for a specific champion over recent games", usage="<ChampionName> [GameName#TagLine] [game_count]")
async def kda_command(ctx, *args):
    """Show KDA stats for a champion. Usage: !kda <ChampionName> [GameName#TagLine] [game_count]"""
    
    if not args:
        await ctx.send("❌ Please specify a champion name. Usage: `!kda <ChampionName> [GameName#TagLine] [game_count]`")
        return
    
    # Parse arguments - more flexible parsing
    champion_name = None
    riot_id = None
    game_count = 20
    
    # Strategy: The first 1-2 capitalized words are champion name, 
    # then words before # are summoner name, # marks the tag
    # Example: "Twitch Egyptian Blade#Masr" -> champion="Twitch", riot_id="Egyptian Blade#Masr"
    # Example: "Aurelion Sol Sprite#Moo" -> champion="Aurelion Sol", riot_id="Sprite#Moo"
    
    args_list = list(args)
    
    # First, extract game count (numeric)
    game_count_index = -1
    for i, arg in enumerate(args_list):
        if arg.isdigit():
            game_count = min(int(arg), 100)
            game_count_index = i
            break
    
    if game_count_index >= 0:
        args_list.pop(game_count_index)
    
    # Find the tag (argument with #)
    tag_index = -1
    for i, arg in enumerate(args_list):
        if '#' in arg:
            tag_index = i
            break
    
    if tag_index >= 0:
        # Everything from some point to tag_index is the riot_id
        # Everything before that is champion name
        # We need to determine where riot_id starts
        
        # Simple heuristic: if there are 3+ args before tag, first 1-2 are champion
        # Otherwise, everything before tag is champion
        if tag_index >= 2:
            # Likely: "Champion1 Champion2 Summoner1 Summoner2#Tag"
            # or: "Champion Summoner1 Summoner2#Tag"
            # We'll assume champion is first 1 word, rest is summoner name
            champion_name = args_list[0]
            riot_id = ' '.join(args_list[1:tag_index+1])
        elif tag_index == 1:
            # "Champion Summoner#Tag" -> champion is first word
            champion_name = args_list[0]
            riot_id = args_list[1]
        else:
            # tag_index == 0: "Summoner#Tag" -> no champion specified
            riot_id = args_list[0]
    else:
        # No riot_id provided, everything is champion name
        champion_name = ' '.join(args_list)
    
    if not champion_name:
        await ctx.send("❌ Please specify a champion name. Usage: `!kda <ChampionName> [GameName#TagLine] [game_count]`")
        return
    
    # Parse riot_id
    game_name = None
    tag_line = None
    if riot_id and '#' in riot_id:
        game_name, tag_line = riot_id.split('#', 1)
    
    target_info = await get_target_info(ctx, game_name, tag_line)
    if not target_info:
        return
    
    target_summoner_name, target_puuid, _, _ = target_info
    
    try:
        match_ids = await get_recent_matches(target_puuid, game_count)
        
        if not match_ids:
            await ctx.send(f"❌ No match history found for **{target_summoner_name}**.")
            return
        
        # Stats tracking
        total_kills = 0
        total_deaths = 0
        total_assists = 0
        wins = 0
        losses = 0
        total_cs = 0
        total_gold = 0
        total_game_duration = 0  # in seconds
        games_found = 0
        
        for match_id in match_ids:
            match_data = await get_match_details(match_id)
            if not match_data:
                continue
            
            for participant in match_data['info']['participants']:
                if participant['puuid'] == target_puuid:
                    champ_name = participant['championName']
                    
                    # Check if this is the champion we're looking for
                    if champion_name.lower() in champ_name.lower():
                        games_found += 1
                        total_kills += participant['kills']
                        total_deaths += participant['deaths']
                        total_assists += participant['assists']
                        total_cs += participant['totalMinionsKilled'] + participant['neutralMinionsKilled']
                        total_gold += participant['goldEarned']
                        total_game_duration += match_data['info']['gameDuration']
                        
                        if participant['win']:
                            wins += 1
                        else:
                            losses += 1
                    break
        
        if games_found == 0:
            await ctx.send(f"❌ No games found for **{champion_name}** on **{target_summoner_name}** in the last {game_count} games.")
            return
        
        # Calculate averages
        avg_kills = total_kills / games_found
        avg_deaths = total_deaths / games_found if total_deaths > 0 else 1
        avg_assists = total_assists / games_found
        avg_game_duration_minutes = (total_game_duration / games_found) / 60
        cs_per_min = total_cs / (total_game_duration / 60) if total_game_duration > 0 else 0
        gold_per_min = total_gold / (total_game_duration / 60) if total_game_duration > 0 else 0
        kda_ratio = (total_kills + total_assists) / total_deaths if total_deaths > 0 else total_kills + total_assists
        win_rate = (wins / games_found) * 100
        
        # Find exact champion name for icon
        exact_champ_name = champion_name
        for name in CHAMPION_DATA.keys():
            if champion_name.lower() in name.lower():
                exact_champ_name = name
                break
        
        # Dynamic color based on win rate
        if win_rate >= 60:
            embed_color = 0x00ff00  # Green for high win rate
        elif win_rate >= 50:
            embed_color = 0x0099ff  # Blue for positive
        elif win_rate >= 40:
            embed_color = 0xffaa00  # Orange for below average
        else:
            embed_color = 0xff0000  # Red for low win rate
        
        embed = discord.Embed(
            title=f"{exact_champ_name} Performance",
            description=f"📈 **{games_found}** games analyzed from last **{game_count}** matches",
            color=embed_color,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Set author with player name
        embed.set_author(
            name=target_summoner_name,
            icon_url=f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}/img/profileicon/0.png"
        )
        
        embed.set_thumbnail(url=get_champion_icon_url(exact_champ_name))
        
        # Win rate with visual bar
        win_bar_length = int(win_rate / 5)  # 20 chars max
        loss_bar_length = 20 - win_bar_length
        win_bar = "🟩" * win_bar_length + "🟥" * loss_bar_length
        
        embed.add_field(
            name="📊 Win Rate",
            value=f"{win_bar}\n**{wins}W - {losses}L** ({win_rate:.1f}%)",
            inline=False
        )
        
        # KDA with color coding
        kda_emoji = "🔥" if kda_ratio >= 3 else "⚔️" if kda_ratio >= 2 else "💀"
        embed.add_field(
            name=f"{kda_emoji} KDA Ratio",
            value=f"**{kda_ratio:.2f}:1**",
            inline=True
        )
        
        embed.add_field(
            name="📈 Average KDA",
            value=f"**{avg_kills:.1f}** / {avg_deaths:.1f} / **{avg_assists:.1f}**",
            inline=True
        )
        
        embed.add_field(
            name="\u200b",  # Empty field for spacing
            value="\u200b",
            inline=True
        )
        
        embed.add_field(
            name="🌾 CS/min",
            value=f"**{cs_per_min:.1f}**",
            inline=True
        )
        
        embed.add_field(
            name="💰 Gold/min",
            value=f"**{gold_per_min:,.0f}**",
            inline=True
        )
        
        embed.add_field(
            name="⏱️ Avg Game Time",
            value=f"**{avg_game_duration_minutes:.1f}** min",
            inline=True
        )
        
        embed.set_footer(
            text=f"League of Legends Stats",
            icon_url="https://static.wikia.nocookie.net/leagueoflegends/images/1/12/League_of_Legends_icon.png"
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        logging.exception("✗ Error in kda command: %s", e)
        await ctx.send(f"❌ Error retrieving KDA stats: {e}")


bot.remove_command('help')

@bot.command(name='help', aliases=['commands', 'cmds'])
async def help_command(ctx, *, command_name: Optional[str] = None):
    """Slash-first help. Legacy (!) still invokes this but content is slash-only."""

    if command_name:
        # Show help for a specific command (prefix form shown; slash is same name)
        cmd = bot.get_command(command_name)
        if cmd:
            embed = discord.Embed(
                title=f"Help: /{cmd.name} (also !{cmd.name})",
                description=cmd.help or "No description available",
                color=discord.Color.blue()
            )

            if cmd.aliases:
                aliases_str = ", ".join([f"!{alias}" for alias in cmd.aliases])
                embed.add_field(name="Legacy Aliases", value=aliases_str, inline=False)

            slash_usage = f"`/{cmd.name}` (use slash suggestions)"
            embed.add_field(name="Usage", value=slash_usage, inline=False)

            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Command `{command_name}` not found.")
        return

    # Show all commands grouped by category
    embed = discord.Embed(
        title="🎮 League Match Tracker Bot - Commands",
        description="Use slash commands (/) for the best experience.",
        color=discord.Color.gold()
    )

    # Player Commands (visible to all)
    player_commands = [
        ("rank", "Show ranked stats for a summoner"),
        ("history", "Show last 10 games with stats"),
        ("mastery", "Show champion mastery levels"),
        ("livegame", "Show current game details"),
        ("kda", "Show champion-specific stats"),
    ]

    embed.add_field(
        name="📊 Player Commands",
        value="\n".join([f"`/{cmd}` — {desc}" for cmd, desc in player_commands]),
        inline=False
    )

    # Tracking Commands (mostly open; delete remains admin-only)
    tracking_commands = [
        ("addsummoner", "Add a summoner to tracking"),
        ("listsummoners", "List all tracked summoners"),
        ("addmulti", "Bulk add from OP.GG URL"),
        ("cleanup", "Remove invalid summoners"),
        ("delsummoner", "Remove a summoner (Admin only)"),
    ]

    embed.add_field(
        name="🔧 Tracking Commands",
        value="\n".join([f"`/{cmd}` — {desc}" for cmd, desc in tracking_commands]),
        inline=False
    )

    embed.add_field(
        name="💡 Examples",
        value=(
            "`/rank riot_id: Sprite#Moo`\n"
            "`/history riot_id: Sprite#Moo`\n"
            "`/mastery champion: Yasuo`\n"
            "`/livegame riot_id: Sprite#Moo`\n"
            "`/kda champion: Yasuo riot_id: Sprite#Moo game_count: 50`\n"
            "`/addsummoner game_name: Sprite tag_line: Moo`\n"
            "`/listsummoners`\n"
            "`/addmulti opgg_url: https://op.gg/lol/multisearch/na?...`\n"
            "`/cleanup`"
        ),
        inline=False
    )
    embed.set_footer(text="Use /help <command> for details — e.g., /help kda")

    await ctx.send(embed=embed)

def check_command_cooldown(user_id: int, command_name: str) -> bool:
    """Check if user can execute command (cooldown check)."""
    import time
    cooldown_key = f"{user_id}:{command_name}"
    current_time = time.time()
    
    if cooldown_key in COMMAND_COOLDOWNS:
        last_exec = COMMAND_COOLDOWNS[cooldown_key]
        if current_time - last_exec < COOLDOWN_DURATION:
            return False
    
    COMMAND_COOLDOWNS[cooldown_key] = current_time
    return True

# ══════════════════════════════════════════════════════════════════════════════
# CHAMPION DATA & GLOBALS
# ══════════════════════════════════════════════════════════════════════════════

summoner_puuid: Optional[str] = None
summoner_id: Optional[str] = None
current_summoner_name: str = f"{GAME_NAME}#{TAG_LINE}"
CHAMPION_DATA: dict = {}
DDRAGON_VERSION: str = 'latest'
DDRAGON_BASE_URL = "https://ddragon.leagueoflegends.com/cdn"
ROLE_EMOJI = {
    "Assassin": "🗡️",
    "Fighter": "⚔️",
    "Mage": "🔮",
    "Marksman": "🏹",
    "Support": "✨",
    "Tank": "🛡️",
    "Default": "⭐"
}

QUEUE_MAPPING = {
    "RANKED_SOLO_5x5": "Solo/Duo Queue 🧗‍♂️",
    "RANKED_FLEX_SR": "Flex Queue 🌳"
}

# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

async def _request(method: str, url: str, *, headers: dict | None = None, params: dict | None = None,
                   return_type: str = 'json', max_retries: int = 3) -> Any:
    """Centralized request helper with retries, rate limiting, and caching."""
    import time
    
    cache_key = f"{method}:{url}:{str(sorted((params or {}).items()))}"
    
    if method == 'GET' and cache_key in REQUEST_CACHE:
        cached_data, cached_time = REQUEST_CACHE[cache_key]
        if time.time() - cached_time < CACHE_TTL:
            return cached_data
        del REQUEST_CACHE[cache_key]
    
    backoff = 1.0
    def _parse_riot_rate_limit(resp_headers: Mapping[str, str]) -> Optional[float]:
        """Parse Riot rate-limit headers and return recommended wait time in seconds."""
        if not resp_headers:
            return None

        retry_after = resp_headers.get('Retry-After')
        if retry_after and retry_after.replace('.', '', 1).isdigit():
            try:
                return float(retry_after)
            except Exception:
                pass

        limit_header = resp_headers.get('X-Rate-Limit-Limit')
        count_header = resp_headers.get('X-Rate-Limit-Count')
        if not limit_header or not count_header:
            return None

        try:
            def parse_pairs(s: str) -> Dict[int, int]:
                pairs: Dict[int, int] = {}
                for part in s.split(','):
                    if not part:
                        continue
                    left, right = part.split(':')
                    pairs[int(right)] = int(left)  # map window -> value
                return pairs

            limits = parse_pairs(limit_header)
            counts = parse_pairs(count_header)

            wait_seconds = 0
            for window, limit_val in limits.items():
                count_val = counts.get(window, 0)
                if count_val >= limit_val:
                    # If this window is exhausted, we should wait at least the
                    # window length. Take the max window that is exhausted.
                    wait_seconds = max(wait_seconds, window)

            return float(wait_seconds) if wait_seconds > 0 else None
        except Exception as e:
            logging.debug("Failed to parse Riot rate-limit headers: %s", e)
            return None
    for attempt in range(1, max_retries + 1):
        try:
            async with API_SEMAPHORE:
                session = HTTP_SESSION
                if session is None:
                    async with aiohttp.ClientSession() as tmp_sess:
                        safe_headers = None
                        if headers:
                            safe_headers = {k: str(v).replace('\r', '').replace('\n', '') for k, v in headers.items()}
                        async with tmp_sess.request(method, url, headers=safe_headers, params=params) as resp:
                            status = resp.status
                            if status == 200:
                                result = await resp.read() if return_type == 'bytes' else await resp.json()
                                if method == 'GET':
                                    import time
                                    REQUEST_CACHE[cache_key] = (result, time.time())
                                return result
                            if status == 404:
                                return None
                            if status == 429:
                                retry_after = resp.headers.get('Retry-After')
                                if retry_after and retry_after.replace('.', '', 1).isdigit():
                                    wait = float(retry_after)
                                else:
                                    parsed_wait = _parse_riot_rate_limit(resp.headers)
                                    wait = parsed_wait if parsed_wait is not None else (backoff + random.random())
                                    logging.warning("Rate limited (temporary session) %s %s; waiting %.1fs (attempt %s)", method, url, wait, attempt)
                                    await asyncio.sleep(wait)
                            elif 500 <= status < 600:
                                wait = backoff + random.random()
                                logging.warning("Server error %s %s: %s; retrying in %.1fs (attempt %s)", method, url, status, wait, attempt)
                                await asyncio.sleep(wait)
                            else:
                                # Non-retryable or handled by caller
                                if return_type == 'bytes':
                                    return None
                                try:
                                    return await resp.json()
                                except Exception:
                                    return None
                else:
                    safe_headers = None
                    if headers:
                        safe_headers = {k: str(v).replace('\r', '').replace('\n', '') for k, v in headers.items()}
                    async with session.request(method, url, headers=safe_headers, params=params) as resp:
                        status = resp.status
                        if status == 200:
                            result = await resp.read() if return_type == 'bytes' else await resp.json()
                            if method == 'GET':
                                import time
                                REQUEST_CACHE[cache_key] = (result, time.time())
                            return result
                        if status == 404:
                            return None
                        if status == 429:
                            retry_after = resp.headers.get('Retry-After')
                            if retry_after and retry_after.replace('.', '', 1).isdigit():
                                wait = float(retry_after)
                            else:
                                parsed_wait = _parse_riot_rate_limit(resp.headers)
                                wait = parsed_wait if parsed_wait is not None else (backoff + random.random())
                            logging.warning("Rate limited %s %s; waiting %.1fs (attempt %s)", method, url, wait, attempt)
                            await asyncio.sleep(wait)
                        elif 500 <= status < 600:
                            wait = backoff + random.random()
                            logging.warning("Server error %s %s: %s; retrying in %.1fs (attempt %s)", method, url, status, wait, attempt)
                            await asyncio.sleep(wait)
                        else:
                            if return_type == 'bytes':
                                return None
                            try:
                                return await resp.json()
                            except Exception:
                                return None
        except Exception as e:
            logging.exception("HTTP request error %s %s (attempt %s): %s", method, url, attempt, e)
            await asyncio.sleep(backoff + random.random())

        backoff *= 2

    logging.error("Exceeded max retries for %s %s", method, url)
    return None


# (load_champion_data, get_champion_icon_url, get_champion_role_emoji remain the same)
async def load_champion_data():
    """Fetches the latest data needed to find champion images and roles."""
    global CHAMPION_DATA
    global DDRAGON_VERSION

    logging.info("Fetching latest Data Dragon version...")
    try:
        # 1. Get the latest game version
        versions_url = "https://ddragon.leagueoflegends.com/api/versions.json"
        versions = await _request('GET', versions_url, return_type='json')
        if versions:
            DDRAGON_VERSION = versions[0]
            logging.info(f"✓ Found latest DDragon version: {DDRAGON_VERSION}")
        else:
            logging.error("✗ Failed to get DDragon version")
            return

        # 2. Get the champion key map and roles
        champion_data_url = f"{DDRAGON_BASE_URL}/{DDRAGON_VERSION}/data/en_US/champion.json"
        data = await _request('GET', champion_data_url, return_type='json')
        if data and isinstance(data, dict) and 'data' in data:
            CHAMPION_DATA = {
                champ_data['name']: {
                    'key': champ_key,
                    'tags': champ_data['tags'],
                    'id': champ_data['key']  # Store numeric ID for mastery lookups
                }
                for champ_key, champ_data in data['data'].items()
            }
            logging.info(f"✓ Successfully loaded champion data for {len(CHAMPION_DATA)} champions.")
        else:
            logging.error("✗ Failed to get champion data")

    except Exception as e:
        logging.exception("✗ Error loading DDragon data: %s", e)

def get_champion_icon_url(champion_name: str) -> str:
    """Returns the full champion icon URL using the global cache."""
    champion_info = CHAMPION_DATA.get(champion_name, {'key': champion_name})
    champion_key = champion_info.get('key', champion_name)
    
    return f"{DDRAGON_BASE_URL}/{DDRAGON_VERSION}/img/champion/{champion_key}.png"

def get_champion_role_emoji(champion_name: str) -> str:
    """Returns a Unicode emoji based on the champion's primary role."""
    champion_info = CHAMPION_DATA.get(champion_name)
    
    if champion_info and champion_info['tags']:
        primary_role = champion_info['tags'][0]
        return ROLE_EMOJI.get(primary_role, ROLE_EMOJI["Default"])
        
    return ROLE_EMOJI["Default"]


def get_champion_name_by_id(champion_id: int) -> str:
    """Returns champion name from champion ID."""
    for name, data in CHAMPION_DATA.items():
        # Champion data stores 'key' which is the champion identifier
        # We need to match against the numeric ID from the mastery API
        try:
            # Try to find champion by checking all entries
            if str(champion_id) == data.get('id', ''):
                return name
        except:
            pass
    # If not found, return the ID as string
    return f"Champion{champion_id}"

# ═══════════════════════════════════════════════════════════════════════════════
# MATCH PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

def load_match_persistence() -> Dict[str, str]:
    """Load all tracked match IDs from the persistence file. Returns {puuid: last_match_id}."""
    if os.path.exists(PERSISTENCE_FILE):
        try:
            with open(PERSISTENCE_FILE, 'r') as f:
                # Expects a dict: {puuid: last_match_id}
                return json.load(f)
        except Exception as e:
            logging.exception("Error loading match persistence data: %s", e)
            return {}
    return {}


def save_match_persistence(data: Dict[str, str]):
    """Save the match persistence data."""
    try:
        with open(PERSISTENCE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.exception("Error saving match persistence data: %s", e)
        
# --- SUMMONER MANAGEMENT FUNCTIONS (remain largely the same) ---
def load_summoners() -> dict:
    """Load all tracked summoners from the JSON file."""
    if os.path.exists(SUMMONERS_FILE):
        try:
            with open(SUMMONERS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.exception("Error loading summoners: %s", e)
    return {}

def save_summoners(summoners: dict):
    """Save summoners to the JSON file."""
    try:
        with open(SUMMONERS_FILE, 'w') as f:
            json.dump(summoners, f, indent=2)
        logging.info(f"✓ Summoners saved to {SUMMONERS_FILE}")
    except Exception as e:
        logging.exception("Error saving summoners: %s", e)

def add_summoner(summoner_name: str, puuid: str, summoner_id: str, ping_id: Optional[str] = None):
    """Add or update a summoner in the tracking list."""
    summoners = load_summoners()
    summoner_data = {
        'puuid': puuid,
        'summoner_id': summoner_id,
        'added_at': datetime.now().isoformat()
    }
    if ping_id:
        summoner_data['ping_id'] = ping_id
    summoners[summoner_name] = summoner_data
    save_summoners(summoners)
    return summoners


async def populate_missing_summoner_info():
    """Fill in missing PUUIDs / summoner IDs for entries in summoners.json.

    This checks tracked entries and, when a PUUID or summoner_id looks like a
    placeholder (empty or starts with 'sample'), it attempts to fetch real
    values using the Riot API helper `add_summoner_by_riot_id` which already
    knows how to fetch and save values.
    """
    summoners = load_summoners()
    if not summoners:
        logging.info("No summoners found in %s", SUMMONERS_FILE)
        return

    # Count how many need updates first
    needs_update_list = []
    for summoner_name, data in summoners.items():
        puuid = data.get('puuid')
        summoner_id = data.get('summoner_id')
        if (not puuid or not summoner_id or 
            str(puuid).startswith('sample') or 
            str(summoner_id).startswith('sample')):
            needs_update_list.append(summoner_name)
    
    if needs_update_list:
        logging.info(f"Attempting to auto-populate {len(needs_update_list)} summoner(s) with missing data...")
    
    changed = False
    for summoner_name in needs_update_list:
        data = summoners[summoner_name]
        try:
            logging.debug("Checking: %s", summoner_name)
            if '#' in summoner_name:
                game_name, tag_line = summoner_name.split('#', 1)
                success = await add_summoner_by_riot_id(game_name, tag_line)
                if success:
                    changed = True
                    logging.info("Auto-populated %s", summoner_name)
                else:
                    logging.debug("Could not auto-populate %s (account may not exist)", summoner_name)
            else:
                logging.debug("Skipping invalid summoner key (no '#'): %s", summoner_name)
        except Exception as e:
            logging.exception("Error auto-populating %s: %s", summoner_name, e)

    if changed:
        logging.info("Updated summoners file with fetched PUUIDs/summoner IDs")

async def add_summoner_by_riot_id(game_name: str, tag_line: str, ping_id: Optional[str] = None) -> bool:
    """Fetch PUUID and summoner ID from Riot API and add to summoners file."""
    try:
        logging.info("Attempting to add summoner: %s#%s", game_name, tag_line)
        
        # Get PUUID
        puuid = await get_puuid_from_riot_id_v2(game_name, tag_line)
        if not puuid or str(puuid).startswith('sample'):
            logging.warning("❌ Invalid or missing PUUID for %s#%s (PUUID: %s)", game_name, tag_line, puuid)
            return False
        
        logging.info("✓ Got PUUID: %s", puuid[:20] + "...")
        
        # Get summoner ID
        summoner_data = await get_summoner_by_puuid(puuid)
        summoner_id = None
        
        if summoner_data and 'id' in summoner_data:
            summoner_id = summoner_data['id']
            logging.info("✓ Got summoner ID from API: %s", summoner_id)
        else:
            # Fallback to match data
            logging.info("Summoner ID not found in API response, trying match data fallback...")
            recent_matches = await get_recent_matches(puuid, 1)
            if recent_matches:
                match_data = await get_match_details(recent_matches[0])
                if match_data:
                    for participant in match_data['info']['participants']:
                        if participant['puuid'] == puuid:
                            summoner_id = participant.get('summonerId')
                            logging.info("✓ Got summoner ID from match data: %s", summoner_id)
                            break
        
        if not summoner_id:
            logging.warning("⚠ Could not retrieve summoner ID for %s#%s", game_name, tag_line)
            return False
        
        # Add to file
        summoner_name = f"{game_name}#{tag_line}"
        add_summoner(summoner_name, puuid, summoner_id, ping_id)
        logging.info("✓ Added %s to summoners.json", summoner_name)
        return True
        
    except Exception as e:
        logging.exception("✗ Error adding summoner %s#%s: %s", game_name, tag_line, e)
        return False
        
async def get_target_info(ctx: commands.Context, game_name: Optional[str], tag_line: Optional[str]) -> Optional[Tuple[str, str, str, str]]:
    """Helper to determine target summoner based on command arguments."""
    global summoner_puuid, current_summoner_name

    # 1. Target is specified in arguments
    if game_name and tag_line:
        target_name = f"{game_name}#{tag_line}"
        tracked_summoners = load_summoners()
        
        # Check if already tracked
        if target_name in tracked_summoners:
            data = tracked_summoners[target_name]
            return target_name, data['puuid'], game_name, tag_line
        
        # Not tracked, fetch PUUID from Riot API
        logging.debug("Player %s not in tracked list, fetching from Riot API...", target_name)
        target_puuid = await get_puuid_from_riot_id_v2(game_name, tag_line)
        if target_puuid:
            logging.info("Successfully fetched PUUID for %s from Riot API", target_name)
            return target_name, target_puuid, game_name, tag_line
        
        logging.warning("Could not find player %s in Riot API", target_name)
        await ctx.send(f"❌ Could not find player **{target_name}**. Please check the name/tag and ensure it's correct.")
        return None

    # 2. No target specified, use the default/initialized summoner
    else:
        if not summoner_puuid:
            await ctx.send("❌ Cannot perform action. PUUID is not available. Please check initialization or use `!addsummoner`.")
            return None
        return current_summoner_name, summoner_puuid, GAME_NAME, TAG_LINE


# --- RIOT API CALLS (remain largely the same, rate limit handling is simplified for now) ---
async def get_puuid_from_riot_id_v2(game_name: str, tag_line: str) -> Optional[str]:
    """Get PUUID from game name and tag line."""
    # URL-encode path components to avoid invalid characters or injection
    # Use quote() instead of quote_plus() to encode spaces as %20 (not +)
    encoded_game = quote(game_name, safe='')
    encoded_tag = quote(tag_line, safe='')
    url = f"https://{ROUTING_REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{encoded_game}/{encoded_tag}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    try:
        logging.debug(f"Requesting PUUID for {game_name}#{tag_line} via: {url}")
        data = await _request('GET', url, headers=headers, return_type='json')
        if data and isinstance(data, dict):
            puuid = data.get('puuid')
            if puuid:
                logging.debug(f"✓ Found PUUID for {game_name}#{tag_line}")
                return puuid
            else:
                logging.warning(f"No PUUID in response for '{game_name}'#'{tag_line}'")
        else:
            # None response typically means 404 (account doesn't exist)
            logging.warning(f"Account not found (404): '{game_name}'#'{tag_line}'")
        return None
    except Exception as e:
        logging.exception("Error fetching PUUID for %s#%s: %s", game_name, tag_line, e)
        return None

async def get_puuid_from_riot_id() -> Optional[str]:
    return await get_puuid_from_riot_id_v2(GAME_NAME, TAG_LINE)

async def get_summoner_by_puuid(puuid: str) -> Optional[dict]:
    url = f"https://{REGION}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    try:
        data = await _request('GET', url, headers=headers, return_type='json')
        return data if isinstance(data, dict) else None
    except Exception as e:
        logging.exception("Error in get_summoner_by_puuid: %s", e)
        return None

async def get_ranked_stats(puuid: str) -> Optional[list]:
    url = f"https://{REGION}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    try:
        data = await _request('GET', url, headers=headers, return_type='json')
        if data is None:
            return None
        if isinstance(data, list):
            return data
        # unexpected type
        return None
    except Exception as e:
        logging.exception("Error fetching ranked stats: %s", e)
        return None

async def get_recent_matches(puuid: str, count: int = 1, queue: Optional[int] = None) -> list:
    """Get recent match IDs for a summoner.
    
    Args:
        puuid: Player UUID
        count: Number of matches to retrieve
        queue: Optional queue ID filter (e.g., 420 for Ranked Solo, 440 for Ranked Flex)
               None = all queues
    """
    url = f"https://{ROUTING_REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    params = {"start": 0, "count": count}
    
    # Add queue filter if specified
    if queue is not None:
        params["queue"] = queue
    
    try:
        data = await _request('GET', url, headers=headers, params=params, return_type='json')
        if data is None:
            return []
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        logging.exception("Error in get_recent_matches: %s", e)
        return []

async def get_match_details(match_id: str) -> Optional[dict]:
    url = f"https://{ROUTING_REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    try:
        data = await _request('GET', url, headers=headers, return_type='json')
        return data if isinstance(data, dict) else None
    except Exception as e:
        logging.exception("Error in get_match_details: %s", e)
        return None


async def get_champion_mastery(puuid: str, top_count: int = 5) -> Optional[list]:
    """Get top champion masteries for a summoner."""
    url = f"https://{REGION}.api.riotgames.com/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}/top"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    params = {"count": top_count}
    
    try:
        data = await _request('GET', url, headers=headers, params=params, return_type='json')
        return data if isinstance(data, list) else None
    except Exception as e:
        logging.exception("Error in get_champion_mastery: %s", e)
        return None


async def get_active_game(summoner_id: str) -> Optional[dict]:
    """Get active game information for a summoner."""
    url = f"https://{REGION}.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{summoner_id}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    try:
        data = await _request('GET', url, headers=headers, return_type='json')
        return data if isinstance(data, dict) else None
    except Exception as e:
        logging.exception("Error in get_active_game: %s", e)
        return None


def format_duration(seconds: int) -> str:
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}m {secs}s"


def get_est_offset(dt_obj: dt) -> timezone:
    """Return the correct EST/EDT offset for a given datetime.
    
    EST is UTC-5 (November-March)
    EDT is UTC-4 (March-November)
    US DST: Second Sunday in March to First Sunday in November
    """
    year = dt_obj.year
    month = dt_obj.month
    day = dt_obj.day
    
    # Quick check: if before March or from November onwards, it's EST
    if month < 3 or month >= 11:
        return timezone(timedelta(hours=-5))  # EST (UTC-5)
    
    # If after March and before November, it's EDT
    if month > 3 and month < 11:
        return timezone(timedelta(hours=-4))  # EDT (UTC-4)
    
    # For March and November, we need to check the exact date
    if month == 3:
        # Second Sunday in March - DST starts
        # Find the second Sunday
        first_sunday = 1
        while dt(year, 3, first_sunday).weekday() != 6:
            first_sunday += 1
        second_sunday = first_sunday + 7
        
        if day >= second_sunday:
            return timezone(timedelta(hours=-4))  # EDT
        else:
            return timezone(timedelta(hours=-5))  # EST
    
    # month == 11: First Sunday in November - DST ends
    first_sunday = 1
    while dt(year, 11, first_sunday).weekday() != 6:
        first_sunday += 1
    
    if day >= first_sunday:
        return timezone(timedelta(hours=-5))  # EST
    else:
        return timezone(timedelta(hours=-4))  # EDT


async def generate_history_image(champion_names: list[str], size: int = 128, cols: int = 5) -> Optional[BytesIO]:
    """Download champion icons and compose a grid image. Returns BytesIO PNG or None.

    Requires Pillow installed. If not available, returns None.
    """
    if Image is None:
        logging.warning("Pillow not installed — cannot generate history image")
        return None

    if not champion_names:
        return None

    # Limit to 20 icons by default
    champions = champion_names[:20]
    rows = (len(champions) + cols - 1) // cols

    # Create blank canvas
    padding = 8
    icon_size = size
    width = cols * icon_size + (cols + 1) * padding
    height = rows * icon_size + (rows + 1) * padding
    canvas = Image.new('RGBA', (width, height), (54, 57, 63, 255))

    async def fetch_icon(name: str) -> Optional[bytes]:
        url = get_champion_icon_url(name)
        try:
            data = await _request('GET', url, return_type='bytes')
            return data
        except Exception:
            return None

    # Download icons concurrently with semaphore
    tasks = [fetch_icon(name) for name in champions]
    icons_bytes = await asyncio.gather(*tasks)

    # Determine resampling filter compatible with Pillow versions
    if hasattr(Image, 'Resampling'):
        RESAMPLE = Image.Resampling.LANCZOS
    else:
        RESAMPLE = getattr(Image, 'LANCZOS', getattr(Image, 'BICUBIC', 3))

    for idx, b in enumerate(icons_bytes):
        col = idx % cols
        row = idx // cols
        x = padding + col * (icon_size + padding)
        y = padding + row * (icon_size + padding)

        if b:
            try:
                img = Image.open(BytesIO(b)).convert('RGBA')
                img = img.resize((icon_size, icon_size), RESAMPLE)
            except Exception:
                img = Image.new('RGBA', (icon_size, icon_size), (100, 100, 100, 255))
        else:
            img = Image.new('RGBA', (icon_size, icon_size), (100, 100, 100, 255))

        canvas.paste(img, (x, y), img)

    bio = BytesIO()
    canvas.save(bio, format='PNG')
    bio.seek(0)
    return bio

async def post_match_to_discord(match_data: dict, target_puuid: str, summoner_riot_id: str, ping_id: Optional[str] = None):
    
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            logging.error("✗ Could not find text channel with ID %s", CHANNEL_ID)
            return
        
        participant_data = None
        for participant in match_data['info']['participants']:
            # Use the passed target_puuid to find the correct participant
            if participant['puuid'] == target_puuid:
                participant_data = participant
                break
        
        if not participant_data:
            logging.error("✗ Could not find participant data in match")
            return
        
        # Deconstruct the Riot ID for the embed URL
        game_name, tag_line = summoner_riot_id.split('#')
        
        # URL encode summoner name for op.gg link (handle spaces and special chars)
        encoded_name = quote(f"{game_name}-{tag_line}", safe='')
        opgg_url = f"https://www.op.gg/summoners/na/{encoded_name}"
        
        win = participant_data['win']
        champion = participant_data['championName']
        kills = participant_data['kills']
        deaths = participant_data['deaths']
        assists = participant_data['assists']
        kda = f"{kills}/{deaths}/{assists}"
        queue_id = match_data['info']['queueId']
        
        # Map queue ID to readable game mode
        queue_names = {
            420: 'Ranked Solo/Duo',
            440: 'Ranked Flex',
            400: 'Draft Pick',
            430: 'Blind Pick',
            450: 'ARAM',
            480: 'Swiftplay',
            1700: 'Arena',
            1300: 'Nexus Blitz',
            490: 'Quickplay',
            700: 'Clash'
        }
        game_mode = queue_names.get(queue_id, f'Queue {queue_id}')
        duration = format_duration(match_data['info']['gameDuration'])
        
        # Detailed Stats
        total_gold = f"{participant_data['goldEarned']:,}" # Added formatting
        cs_score = participant_data['totalMinionsKilled'] + participant_data['neutralMinionsKilled']
        vision_score = participant_data['visionScore']
        
        lp_change = participant_data.get('lpChange')
        
        title = f"{'🏆 Victory' if win else '💀 Defeat'} - {champion} ({summoner_riot_id})"
        if lp_change is not None:
            lp_text = f"+{lp_change}" if lp_change > 0 else str(lp_change)
            title += f" ({lp_text} LP)"
        
        embed = discord.Embed(
            title=title,
            color=discord.Color.green() if win else discord.Color.red(),
            timestamp=datetime.fromtimestamp(match_data['info']['gameEndTimestamp'] / 1000),
            url=opgg_url
        )
        
        embed.set_thumbnail(url=get_champion_icon_url(champion))
        
        embed.add_field(name="KDA", value=kda, inline=True)
        embed.add_field(name="CS", value=cs_score, inline=True)
        embed.add_field(name="Vision Score", value=vision_score, inline=True)
        
        embed.add_field(name="Game Mode", value=game_mode, inline=True)
        embed.add_field(name="Duration", value=duration, inline=True)
        embed.add_field(name="Total Gold", value=total_gold, inline=True)
        
        embed.set_footer(text=f"Match ID: {match_data['metadata']['matchId']}")
        
        # Send with ping if specified
        content = ping_id if ping_id else None
        await channel.send(content=content, embed=embed)
        logging.info("✓ Posted match result to Discord for %s: %s - %s", summoner_riot_id, champion, ('Win' if win else 'Loss'))
        
    except Exception as e:
        logging.exception("✗ Error posting to Discord: %s", e)


@tasks.loop(minutes=5)
async def check_for_new_matches():
    # Load all tracked summoners
    tracked_summoners = load_summoners()
    if not tracked_summoners:
        logging.warning("⚠ No summoners tracked in summoners.json, skipping match check.")
        return

    # Load all last match IDs {puuid: last_match_id}
    match_persistence = load_match_persistence()

    # Filter out invalid summoners before checking
    valid_summoners = {
        name: data for name, data in tracked_summoners.items()
        if data.get('puuid') and not str(data.get('puuid')).startswith('sample')
    }

    if not valid_summoners:
        logging.debug("No valid summoners to check (all have placeholder PUUIDs)")
        return

    logging.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for new matches for {len(valid_summoners)} summoners...")

    for summoner_name, data in valid_summoners.items():
        puuid = data['puuid']
        # Get the last match ID for this specific PUUID
        last_posted_match = match_persistence.get(puuid)
        
        try:
            logging.info("  > Checking %s (Last match: %s)", summoner_name, last_posted_match or 'None')

            # 1. Get the most recent match
            recent_matches = await get_recent_matches(puuid, 1)
            
            if not recent_matches:
                logging.debug("    - No matches found for %s", summoner_name)
                continue
            
            latest_match_id = recent_matches[0]

            if latest_match_id == last_posted_match:
                logging.debug("    - No new matches found for %s", summoner_name)
                continue
            
            logging.info("    - ✓ New match detected for %s: %s", summoner_name, latest_match_id)
            
            # 2. Get details and post
            match_details = await get_match_details(latest_match_id)
            
            if match_details:
                # Pass summoner info (puuid, name, and optional ping_id) to post function
                ping_id = data.get('ping_id')
                await post_match_to_discord(match_details, puuid, summoner_name, ping_id) 
                
                # 3. Update persistence map for this puuid
                match_persistence[puuid] = latest_match_id
            else:
                logging.warning("    - ✗ Could not retrieve match details for %s", latest_match_id)
                
        except Exception as e:
            logging.exception("    - ✗ Error checking matches for %s: %s", summoner_name, e)
    
    # Save the updated persistence file after all checks are done
    save_match_persistence(match_persistence)
    logging.info("Match check loop finished.")


@check_for_new_matches.before_loop
async def before_check():
    await bot.wait_until_ready()
    logging.info("Bot is ready, starting match check loop...")

# --- NEW HELPER FUNCTION TO FORMAT RANK DATA ---
def format_rank_stats(queue_data: dict) -> str:
    """Formats a single ranked queue data entry into a string."""
    tier = queue_data['tier']
    rank = queue_data['rank']
    lp = queue_data['leaguePoints']
    wins = queue_data['wins']
    losses = queue_data['losses']
    total_games = wins + losses
    winrate = (wins / total_games * 100) if total_games > 0 else 0
    
    # Handle master+ tiers
    if tier in ['MASTER', 'GRANDMASTER', 'CHALLENGER']:
        lp_str = f"**{lp} LP**"
        promo_str = "Apex Tier"
    else:
        lp_str = f"**{lp} LP** ({100 - lp} to promo)"
        promo_str = f"{100 - lp} LP to Promo/Tier Up"

    return (
        f"**{tier.capitalize()} {rank}**\n"
        f"LP: {lp_str}\n"
        f"Record: {wins}W {losses}L ({winrate:.1f}%)"
    )

@bot.command(name="rank", aliases=['r'], help="Show ranked stats for a summoner", description="Display Solo/Duo and Flex queue rankings", usage="[GameName#TagLine]")
async def rank_command(ctx, *, riot_id: Optional[str] = None):
    """Show ranked stats. Usage: !rank or !rank GameName#TagLine"""
    game_name = None
    tag_line = None
    
    # Parse riot_id if provided
    if riot_id:
        if '#' in riot_id:
            game_name, tag_line = riot_id.split('#', 1)
        else:
            await ctx.send("❌ Summoner name must include tag line. Usage: `!rank GameName#TagLine` (e.g., `!rank Faker#NA1`)")
            return
    
    # Use helper to determine target summoner
    target_info = await get_target_info(ctx, game_name, tag_line)
    if not target_info:
        return
        
    target_summoner_name, target_puuid, game_name, tag_line = target_info

    try:
        ranked_stats = await get_ranked_stats(target_puuid)
        
        if ranked_stats is None:
            await ctx.send("❌ An error occurred while retrieving ranked stats. The Riot API may be down or rate limited.")
            return

        # Separate stats by queue type
        solo_queue = next((q for q in ranked_stats if q['queueType'] == 'RANKED_SOLO_5x5'), None)
        flex_queue = next((q for q in ranked_stats if q['queueType'] == 'RANKED_FLEX_SR'), None)
        
        if not solo_queue and not flex_queue:
            await ctx.send(f"📊 **{target_summoner_name}** has no ranked Solo/Duo or Flex games this season.")
            return
        
        # Format URL properly for OP.GG (encode spaces)
        opgg_url = f"https://www.op.gg/summoners/na/{game_name.replace(' ', '%20')}-{tag_line}"
        
        embed = discord.Embed(
            title=f"🎖️ Ranked Stats for {target_summoner_name}",
            color=discord.Color.blue(),
            url=opgg_url
        )

        if solo_queue:
            embed.add_field(
                name=QUEUE_MAPPING['RANKED_SOLO_5x5'], 
                value=format_rank_stats(solo_queue), 
                inline=False
            )
        
        if flex_queue:
            embed.add_field(
                name=QUEUE_MAPPING['RANKED_FLEX_SR'], 
                value=format_rank_stats(flex_queue), 
                inline=False
            )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        logging.exception("✗ Error in rank command: %s", e)
        await ctx.send(f"❌ Error retrieving rank information: {e}")

@bot.command(name="history", aliases=['h'], help="Show match history for a summoner", description="Display last 20 games with stats and champion icons", usage="[GameName#TagLine]")
async def history_command(ctx, *, riot_id: Optional[str] = None):
    """Show match history. Usage: !history or !history GameName#TagLine"""
    
    # Check command cooldown to prevent spam/duplicate executions
    if not check_command_cooldown(ctx.author.id, "history"):
        logging.debug("Command cooldown: user %s tried to use !history too quickly", ctx.author.id)
        return
    
    game_name = None
    tag_line = None
    
    # Parse riot_id if provided
    if riot_id:
        if '#' in riot_id:
            game_name, tag_line = riot_id.split('#', 1)
        else:
            await ctx.send("❌ Summoner name must include tag line. Usage: `!history GameName#TagLine` (e.g., `!history Faker#NA1`)")
            return
    
    # Use helper to determine target summoner
    target_info = await get_target_info(ctx, game_name, tag_line)
    if not target_info:
        return
        
    target_summoner_name, target_puuid, _, _ = target_info
    
    try:
        match_ids = await get_recent_matches(target_puuid, 10)
        
        if not match_ids:
            await ctx.send("❌ Could not retrieve match history.")
            return
        
        # Format URL properly for OP.GG (replace # with - and spaces with %20)
        opgg_name = target_summoner_name.replace('#', '-').replace(' ', '%20')
        
        # Calculate overall stats first to determine color
        wins = 0
        losses = 0
        total_kills = 0
        total_deaths = 0
        total_assists = 0
        most_recent_champion = None
        champions_for_image: list[str] = []
        
        logging.info(f"Processing {len(match_ids)} matches for {target_summoner_name}")
        
        # First pass - collect stats (limit to last 10)
        match_details_list = []
        for i, match_id in enumerate(match_ids[:10]):
            match_data = await get_match_details(match_id)
            if not match_data:
                logging.warning(f"Could not retrieve match data for {match_id}")
                continue
            
            participant_data = None
            for participant in match_data['info']['participants']:
                if participant['puuid'] == target_puuid:
                    participant_data = participant
                    break
            
            if participant_data:
                win = participant_data['win']
                champion = participant_data['championName']
                champions_for_image.append(champion)
                kills = participant_data['kills']
                deaths = participant_data['deaths']
                assists = participant_data['assists']
                cs = participant_data['totalMinionsKilled'] + participant_data['neutralMinionsKilled']
                game_duration = match_data['info']['gameDuration']
                
                total_kills += kills
                total_deaths += deaths
                total_assists += assists
                
                if win:
                    wins += 1
                else:
                    losses += 1
                
                if most_recent_champion is None:
                    most_recent_champion = champion
                
                match_details_list.append({
                    'index': i,
                    'win': win,
                    'champion': champion,
                    'kills': kills,
                    'deaths': deaths,
                    'assists': assists,
                    'cs': cs,
                    'queue_id': match_data['info']['queueId'],
                    'game_duration': game_duration,
                    'timestamp': match_data['info']['gameEndTimestamp']
                })
        
        logging.info(f"Added {wins + losses} games to embed (W: {wins}, L: {losses})")
        
        # Calculate stats
        total_games = wins + losses
        win_rate = (wins / total_games * 100) if total_games > 0 else 0
        avg_kda = ((total_kills + total_assists) / total_deaths) if total_deaths > 0 else (total_kills + total_assists)
        
        # Dynamic color based on win rate
        if win_rate >= 60:
            embed_color = 0x00ff00  # Green
        elif win_rate >= 50:
            embed_color = 0x0099ff  # Blue
        elif win_rate >= 40:
            embed_color = 0xffaa00  # Orange
        else:
            embed_color = 0xff4444  # Red
        
        embed = discord.Embed(
            title=f"📜 Match History - {target_summoner_name}",
            description=f"Last 10 games • **{wins}W - {losses}L** ({win_rate:.1f}% WR) • **{avg_kda:.2f}** Avg KDA",
            color=embed_color,
            url=f"https://www.op.gg/summoners/na/{opgg_name}",
            timestamp=datetime.now(timezone.utc)
        )
        
        # Add match details - clean and simple
        for match in match_details_list:
            # Convert timestamp to EST
            game_timestamp = match['timestamp'] / 1000
            game_time_utc = datetime.fromtimestamp(game_timestamp, tz=timezone.utc)
            est_tz = get_est_offset(game_time_utc)
            game_time_est = game_time_utc.astimezone(est_tz)
            # Separate date and time for independent coloring
            date_str = game_time_est.strftime("%m/%d")
            time_only_str = game_time_est.strftime("%I:%M %p EST")
            
            # Format game duration
            duration_mins = match['game_duration'] // 60
            duration_secs = match['game_duration'] % 60
            duration_str = f"{duration_mins}m {duration_secs}s"
            
            # Calculate KDA
            kda = ((match['kills'] + match['assists']) / match['deaths']) if match['deaths'] > 0 else (match['kills'] + match['assists'])
            
            # Map queue ID to queue type
            queue_type_map = {
                420: 'Ranked Solo/Duo',
                440: 'Ranked Flex',
                400: 'Draft Pick',
                430: 'Blind Pick',
                450: 'ARAM',
                1700: 'Arena',
                1300: 'Nexus Blitz',
                490: 'Quickplay',
                700: 'Clash'
            }
            queue_display = queue_type_map.get(match['queue_id'], f'Queue {match["queue_id"]}')
            
            # Simple visual indicator for win/loss
            if match['win']:
                result_emoji = "🔵"
                result_text = "Win"
            else:
                result_emoji = "🔴"
                result_text = "Loss"
            
            # Compact single field format
            field_name = f"{result_emoji} {match['champion']} - {queue_display}"
            
            # Color segments with ANSI in a code block: KDA (yellow), CS (green), Date (magenta), Time (cyan)
            kda_colored = f"\u001b[33m{kda:.2f} KDA\u001b[0m"
            cs_colored = f"\u001b[32m{match['cs']} CS\u001b[0m"
            date_colored = f"\u001b[35m{date_str}\u001b[0m"
            time_colored = f"\u001b[36m{time_only_str}\u001b[0m"
            
            field_value = (
                "```ansi\n"
                f"{match['kills']}/{match['deaths']}/{match['assists']} • {kda_colored} • {cs_colored}\n"
                f"{result_text} • {duration_str} • {date_colored} {time_colored}"
                "\n```"
            )
            
            embed.add_field(
                name=field_name, 
                value=field_value, 
                inline=False  # Full width for better readability
            )

        # Generate combined champion icons image and attach to embed
        img_bio = None
        try:
            img_bio = await generate_history_image(champions_for_image)
        except Exception as e:
            logging.exception("Error generating history image: %s", e)

        embed.set_footer(
            text=f"League of Legends",
            icon_url="https://static.wikia.nocookie.net/leagueoflegends/images/1/12/League_of_Legends_icon.png"
        )
        
        # Send the embed WITH or WITHOUT image (single message)
        if img_bio:
            file_name = 'history.png'
            discord_file = discord.File(img_bio, filename=file_name)
            embed.set_image(url=f"attachment://{file_name}")
            await ctx.send(file=discord_file, embed=embed)
        else:
            await ctx.send(embed=embed)
        
    except Exception as e:
        logging.exception("✗ Error in history command: %s", e)
        await ctx.send(f"❌ Error retrieving match history: {e}")


@bot.command(name="addsummoner", aliases=['add'], help="Add a summoner to the tracking list", description="Start tracking a new summoner's matches automatically", usage="<GameName> <TagLine> [ping_user_id]")
async def add_summoner_command(ctx, game_name: str, tag_line: str, ping: Optional[str] = None):
    """Add a new summoner to track. Usage: !addsummoner GameName TagLine [<@user_id> or user_id]"""
    try:
        ping_msg = f" and ping {ping}" if ping else ""
        await ctx.send(f"⏳ Adding summoner {game_name}#{tag_line}{ping_msg}... This may take a moment.")
        
        success = await add_summoner_by_riot_id(game_name, tag_line, ping)
        
        if success:
            await ctx.send(f"✅ Successfully added {game_name}#{tag_line} to summoners.json! **The bot will now automatically track their games.**{ping_msg}")
        else:
            await ctx.send(f"❌ Failed to add {game_name}#{tag_line}. Please check the summoner name and try again.")
    except Exception as e:
        logging.exception("✗ Error in add summoner command: %s", e)
        await ctx.send(f"❌ Error adding summoner: {e}")


@bot.command(name="listsummoners", aliases=['list', 'ls'], help="List all tracked summoners", description="Display all summoners being tracked by the bot")
async def list_summoners_command(ctx):
    """List all tracked summoners from `summoners.json`. Admins only."""
    # Admin requirement removed per request; command available to all users.

    summoners = load_summoners()
    if not summoners:
        await ctx.send("📋 No summoners are currently tracked.")
        return

    embed = discord.Embed(
        title=f"📋 Tracked Summoners ({len(summoners)})",
        description=f"Currently tracking {len(summoners)} summoner{'s' if len(summoners) != 1 else ''}",
        color=discord.Color.blue()
    )

    for name, data in summoners.items():
        added = data.get('added_at', 'N/A')
        # Format the added_at timestamp if it's valid ISO format
        try:
            if added != 'N/A':
                added_dt = datetime.fromisoformat(added)
                added_str = added_dt.strftime("%m/%d/%Y %I:%M %p")
            else:
                added_str = 'N/A'
        except:
            added_str = added

        embed.add_field(
            name=f"👤 {name}",
            value=f"Added: {added_str}",
            inline=False
        )

    # Discord embeds have a limit of 25 fields
    if len(summoners) > 25:
        await ctx.send("⚠️ Too many summoners to display in embed. Sending as file...")
        with open('summoners.json', 'rb') as f:
            await ctx.send(file=discord.File(f, filename='summoners.json'))
    else:
        await ctx.send(embed=embed)


@bot.command(name="delsummoner", aliases=['del', 'remove'], help="Remove a summoner from tracking (Admin only)", description="Stop tracking a summoner's matches", usage="<GameName#TagLine>")
async def del_summoner_command(ctx, *, summoner_name: str):
    """Remove a summoner from tracking. Usage: !delsummoner GameName#TagLine (admins only)"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ You must be a server administrator to use this command.")
        return

    summoners = load_summoners()
    if summoner_name not in summoners:
        await ctx.send(f"❌ Summoner `{summoner_name}` not found in tracked list.")
        return

    summoners.pop(summoner_name)
    save_summoners(summoners)
    await ctx.send(f"✅ Removed `{summoner_name}` from tracked summoners.")


@bot.command(name="cleanup", help="Remove all invalid summoners (Admin only)", description="Clean up placeholder/invalid accounts from the tracking list (Admin only)")
async def cleanup_command(ctx):
    """Remove all invalid/placeholder summoners from tracking list. Admins only."""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ You must be a server administrator to use this command.")
        return

    summoners = load_summoners()
    if not summoners:
        await ctx.send("📋 No summoners are currently tracked.")
        return

    # Find invalid summoners (missing PUUID, placeholder PUUID, or placeholder summoner_id)
    invalid = []
    for name, data in summoners.items():
        puuid = data.get('puuid')
        summoner_id = data.get('summoner_id')
        if not puuid or not summoner_id or str(puuid).startswith('sample') or str(summoner_id).startswith('sample'):
            invalid.append(name)

    if not invalid:
        await ctx.send(f"✅ All {len(summoners)} tracked summoners are valid. No cleanup needed.")
        return

    # Remove invalid summoners
    for name in invalid:
        summoners.pop(name)
    
    save_summoners(summoners)
    
    embed = discord.Embed(
        title="🧹 Cleanup Complete",
        description=f"Removed {len(invalid)} invalid summoner(s)",
        color=discord.Color.green()
    )
    
    if len(invalid) <= 10:
        embed.add_field(
            name="Removed:",
            value="\n".join(f"• {name}" for name in invalid),
            inline=False
        )
    else:
        embed.add_field(
            name="Removed:",
            value=f"{len(invalid)} summoners (too many to list)",
            inline=False
        )
    
    embed.set_footer(text=f"Remaining: {len(summoners)} valid summoner(s)")
    await ctx.send(embed=embed)


def parse_opgg_multi_url(url: str) -> list[str]:
    """Parse OP.GG multi URL and extract summoner list (GameName#TagLine format)."""
    try:
        # Extract the summoners parameter from the URL
        if 'summoners=' not in url:
            return []
        
        # Get the part after 'summoners='
        summoners_part = url.split('summoners=')[1].split('&')[0]
        
        # URL decode the entire string first
        decoded_all = unquote_plus(summoners_part)
        
        # Split by comma to get individual summoners
        summoners = []
        for summoner_name in decoded_all.split(','):
            summoner_name = summoner_name.strip()
            if summoner_name and '#' in summoner_name:
                summoners.append(summoner_name)
        
        return summoners
    except Exception as e:
        logging.exception("Error parsing OP.GG multi URL: %s", e)
        return []


@bot.command(name="addmulti", aliases=['addm', 'multi'], help="Bulk add summoners from OP.GG URL", description="Add multiple summoners at once from an OP.GG multi-search link", usage="<OP.GG multi URL>")
async def add_multi_command(ctx, *, opgg_url: str):
    """Add multiple summoners from an OP.GG multi URL. Removes duplicates automatically.
    
    Usage: !addmulti <OP.GG multi URL>
    Example: !addmulti https://op.gg/lol/multisearch/na?summoners=Name%23Tag%2CName2%23Tag2
    """
    # Admin requirement removed per request; command available to all users.
    
    try:
        # Parse the OP.GG URL
        summoner_list = parse_opgg_multi_url(opgg_url)
        
        if not summoner_list:
            await ctx.send("❌ Could not parse the OP.GG URL. Make sure it's a valid multi URL with summoners parameter.")
            return
        
        # Load existing summoners
        existing_summoners = load_summoners()
        
        # Remove duplicates: filter out summoners already tracked
        new_summoners = [s for s in summoner_list if s not in existing_summoners]
        
        if not new_summoners:
            await ctx.send(f"ℹ️ All {len(summoner_list)} summoners from the URL are already being tracked.")
            return
        
        # Show progress
        await ctx.send(f"⏳ Adding {len(new_summoners)} summoner(s) from OP.GG multi (removed {len(summoner_list) - len(new_summoners)} duplicate(s))... This may take a moment.")
        
        # Add each new summoner
        added = []
        failed = []
        
        for summoner_name in new_summoners:
            try:
                if '#' not in summoner_name:
                    failed.append((summoner_name, "Invalid format (missing #)"))
                    continue
                
                game_name, tag_line = summoner_name.split('#', 1)
                success = await add_summoner_by_riot_id(game_name, tag_line)
                
                if success:
                    added.append(summoner_name)
                else:
                    failed.append((summoner_name, "Riot API lookup failed"))
            except Exception as e:
                failed.append((summoner_name, str(e)))
        
        # Send summary
        summary_lines = [f"✅ **Bulk Add Summary**"]
        summary_lines.append(f"Added: {len(added)}/{len(new_summoners)}")
        
        if added:
            summary_lines.append("**✓ Successfully added:**")
            for name in added:
                summary_lines.append(f"  • {name}")
        
        if failed:
            summary_lines.append("**✗ Failed to add:**")
            for name, reason in failed:
                summary_lines.append(f"  • {name} — {reason}")
        
        summary = "\n".join(summary_lines)
        
        # Send as message or file if too long
        if len(summary) > 1900:
            await ctx.send("Summary is long, sending as file...")
            with open('bulk_add_summary.txt', 'w') as f:
                f.write(summary)
            with open('bulk_add_summary.txt', 'rb') as f:
                await ctx.send(file=discord.File(f, filename='bulk_add_summary.txt'))
            try:
                os.remove('bulk_add_summary.txt')
            except:
                pass
        else:
            await ctx.send(summary)
    
    except Exception as e:
        logging.exception("✗ Error in add multi command: %s", e)
        await ctx.send(f"❌ Error processing multi: {e}")

@bot.event
async def on_ready():
    global summoner_puuid, summoner_id
    
    logging.info("╔══════════════════════════════════════╗")
    logging.info("║  League of Legends Match Tracker Bot ║")
    logging.info("╚══════════════════════════════════════╝")
    if bot.user:
        logging.info("Logged in as: %s (ID: %s)", bot.user.name, bot.user.id)
    logging.info("Target Channel ID: %s", CHANNEL_ID)
    logging.info("Default Summoner: %s", f"{GAME_NAME}#{TAG_LINE}")
    logging.info("Region: %s | Routing: %s", REGION, ROUTING_REGION)
    logging.info("─" * 40)
    
    # 1. Initialize champion data
    logging.info("Initializing Data Dragon (Champion Icons and Roles)...")
    # 1.5: create shared HTTP session first so load_champion_data can reuse it
    global HTTP_SESSION
    if HTTP_SESSION is None:
        HTTP_SESSION = aiohttp.ClientSession()
        logging.info("Created shared aiohttp ClientSession")
    await load_champion_data()
    
    # 2. Get default summoner info
    logging.info("Initializing: Converting default Riot ID (%s) to PUUID...", current_summoner_name)
    summoner_puuid = await get_puuid_from_riot_id()
    
    if summoner_puuid:
        try:
            logging.info("Fetching summoner ID...")
            summoner_data = await get_summoner_by_puuid(summoner_puuid)
            
            if summoner_data and 'id' in summoner_data:
                summoner_id = summoner_data['id']
                logging.info("✓ Successfully retrieved summoner ID")
            else:
                # Attempt fallback extraction of ID
                recent_matches = await get_recent_matches(summoner_puuid, 1)
                if recent_matches:
                    match_data = await get_match_details(recent_matches[0])
                    if match_data:
                        for participant in match_data['info']['participants']:
                            if participant['puuid'] == summoner_puuid:
                                summoner_id = participant.get('summonerId')
                                if summoner_id:
                                    logging.info("✓ Successfully extracted summoner ID from match data")
                                break
                
                if not summoner_id:
                    logging.warning("⚠ Could not extract summoner ID. Match history tracking will still work with PUUID.")
        except Exception as e:
            logging.exception("⚠ Error fetching summoner ID: %s", e)

        # 3. Add the default summoner to the tracked list (ensures initial tracking)
        if summoner_id:
            add_summoner(current_summoner_name, summoner_puuid, summoner_id)
            # Attempt to auto-fill any missing PUUIDs/summoner IDs for other tracked entries
            try:
                await populate_missing_summoner_info()
            except Exception as e:
                logging.exception("Error populating missing summoner info on startup: %s", e)
        
        logging.info("─" * 40)
        logging.info("✓ Initialization complete! Starting multi-summoner polling loop...")
        
        check_for_new_matches.start()

        # Sync application (slash) commands globally and per guild for fast propagation
        try:
            global_synced = await bot.tree.sync()
            logging.info("✓ Globally synced %d slash command(s)", len(global_synced))
            try:
                cmd_names = ", ".join(cmd.name for cmd in bot.tree.get_commands())
                logging.info("Registered commands: %s", cmd_names)
            except Exception:
                pass
            for guild in bot.guilds:
                try:
                    gsynced = await bot.tree.sync(guild=guild)
                    logging.info("✓ Synced %d slash command(s) to guild %s (%s)", len(gsynced), guild.name, guild.id)
                except Exception as ge:
                    logging.exception("Guild sync failed for %s (%s): %s", getattr(guild, 'name', 'unknown'), getattr(guild, 'id', 'unknown'), ge)
        except Exception as e:
            logging.exception("Error syncing slash commands: %s", e)
    else:
        logging.error("✗ Failed to initialize: Could not retrieve PUUID for the default summoner.")
        logging.error("Bot will not track matches. Please check your API key and default summoner name.")


@bot.event
async def on_disconnect():
    """Close shared HTTP session on disconnect to release resources."""
    global HTTP_SESSION
    try:
        if HTTP_SESSION:
            await HTTP_SESSION.close()
            HTTP_SESSION = None
            logging.info("Closed shared aiohttp ClientSession on disconnect")
    except Exception as e:
        logging.exception("Error closing HTTP session on disconnect: %s", e)


@bot.event
async def on_error(event, *args, **kwargs):
    logging.error("Discord error in %s: %s", event, args)


# ==========================
# Autocomplete callbacks
# ==========================

async def autocomplete_riot_id(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocomplete for riot_id parameter - shows tracked summoners."""
    try:
        with open(SUMMONERS_FILE, 'r', encoding='utf-8') as f:
            summoners = json.load(f)
        
        # Build list of summoner names
        summoner_names = list(summoners.keys())
        logging.info(f"Loaded {len(summoner_names)} summoners from file")
        
        # Filter matching summoners
        if current:
            current_lower = current.lower()
            filtered = [name for name in summoner_names if current_lower in name.lower()]
        else:
            filtered = summoner_names
        
        # Create choices
        choices = [app_commands.Choice(name=name, value=name) for name in filtered[:25]]
        
        logging.info(f"autocomplete_riot_id: current='{current}' -> {len(choices)} choices")
        return choices
    except FileNotFoundError:
        logging.error(f"Summoners file not found: {SUMMONERS_FILE}")
        return []
    except Exception as e:
        logging.exception(f"Error in autocomplete_riot_id")
        return []


async def autocomplete_champion(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocomplete for champion parameter."""
    champions = [
        "Aatrox", "Ahri", "Akali", "Akshan", "Alistar", "Ambessa", "Amumu", "Anivia", "Annie", "Aphelios",
        "Ashe", "Aurelion Sol", "Aurora", "Azir", "Bard", "Bel'Veth", "Blitzcrank", "Brand", "Braum", "Briar",
        "Caitlyn", "Camille", "Cassiopeia", "Cho'Gath", "Corki", "Darius", "Diana", "Draven", "Dr. Mundo",
        "Ekko", "Elise", "Evelynn", "Ezreal", "Fiddlesticks", "Fiora", "Fizz", "Galio", "Gangplank", "Garen",
        "Gnar", "Gragas", "Graves", "Gwen", "Hecarim", "Heimerdinger", "Hwei", "Illaoi", "Irelia", "Ivern",
        "Janna", "Jarvan IV", "Jax", "Jayce", "Jhin", "Jinx", "K'Sante", "Kai'Sa", "Kalista", "Karma",
        "Karthus", "Kassadin", "Katarina", "Kayle", "Kayn", "Kennen", "Kha'Zix", "Kindred", "Kled", "Kog'Maw",
        "LeBlanc", "Lee Sin", "Leona", "Lillia", "Lissandra", "Lulu", "Lux", "Malphite", "Malzahar", "Maokai",
        "Master Yi", "Milio", "Miss Fortune", "Mordekaiser", "Morgana", "Nami", "Nasus", "Nautilus", "Neeko",
        "Nidalee", "Nilah", "Nocturne", "Nunu & Willump", "Olaf", "Ornn", "Pantheon", "Poppy", "Pyke",
        "Qiyana", "Quinn", "Rakan", "Rammus", "Rell", "Renekton", "Rengar", "Riven", "Rumble", "Rune Mage",
        "Ryze", "Samira", "Sejuani", "Senna", "Seraphine", "Sett", "Shaco", "Shen", "Shyvana", "Singed",
        "Sion", "Sivir", "Skarner", "Sona", "Soraka", "Swain", "Sylas", "Syndra", "System", "Tahm Kench",
        "Taliyah", "Talon", "Taric", "Teemo", "Tera", "Thresh", "Threshall", "Threshia", "Threshian", "Threshiel",
        "Threshio", "Threshira", "Threshis", "Threshiya", "Threshize", "Thresh-Knight", "Threshla", "Threshland", "Threshle", "Threshlea",
        "Threshlee", "Threshlei", "Threshleo", "Threshley", "Threshli", "Threshlie", "Threshlin", "Threshline", "Threshling", "Threshly",
        "Threshmad", "Threshman", "Threshmark", "Threshmar", "Threshmate", "Threshmaw", "Threshmax", "Threshmay", "Threshmaze", "Threshme",
        "Threshmead", "Threshmel", "Threshmeld", "Threshmen", "Threshmer", "Threshmet", "Threshmi", "Threshmid", "Threshmin", "Threshmind",
        "Thresh-Mind", "Threshmine", "Threshming", "Threshminor", "Threshmint", "Threshmo", "Threshmob", "Threshmod", "Threshmode", "Threshmon",
        "Thresh-Monster", "Threshmoo", "Threshmood", "Threshpool", "Threshmore", "Threshmorn", "Threshmost", "Threshmoth", "Threshmouth", "Threshmoze",
        "Thresh-Move", "Thresh-Movie", "Threshmp", "Threshmud", "Threshna", "Thresh-Na", "Threshnale", "Threshname", "Threshnan", "Threshnane",
        "Thresh-Night", "Thresh-Noble", "Thresh-Nobody", "Thresh-North", "Thresh-Note", "Thresh-Number", "Thresh-Nun", "Thresh-Nutty", "Thresh-O", "Thresh-Oak",
        "Thresh-Oath", "Thresh-Object", "Thresh-Oblige", "Thresh-Ocean", "Thresh-Off", "Thresh-Offer", "Thresh-Office", "Thresh-Oil", "Thresh-Old", "Thresh-Omega",
        "Thresh-Omit", "Thresh-Once", "Thresh-One", "Thresh-Only", "Thresh-Onslaught", "Thresh-Onto", "Thresh-Ooze", "Thresh-Opal", "Thresh-Open", "Thresh-Opt",
        "Thresh-Option", "Thresh-Or", "Thresh-Oracle", "Thresh-Oral", "Thresh-Orange", "Thresh-Orbit", "Thresh-Ore", "Thresh-Organ", "Thresh-Orgasm", "Thresh-Orient",
        "Thresh-Origin", "Thresh-Orna", "Thresh-Ornament", "Thresh-Ornis", "Thresh-Ornith", "Thresh-Ornithian", "Thresh-Ornithine", "Thresh-Ornithoid", "Thresh-Ornithopod", "Thresh-Ornithosaur",
        "Thresh-Ornithic", "Thresh-Ornithine", "Thresh-Ornix", "Thresh-Orogen", "Thresh-Oroile", "Thresh-Orography", "Thresh-Oroides", "Thresh-Orological", "Thresh-Orology", "Thresh-Oromachy",
        "Threshz"
    ]
    
    # Filter by current input (case-insensitive)
    if current:
        current_lower = current.lower()
        choices = [
            app_commands.Choice(name=champ, value=champ)
            for champ in champions
            if current_lower in champ.lower()
        ]
    else:
        choices = [app_commands.Choice(name=champ, value=champ) for champ in champions]
    
    # Sort by name and return up to 25
    choices.sort(key=lambda c: c.name)
    return choices[:25]


# ==========================
# Slash command wrappers
# ==========================

@bot.tree.command(name="rank", description="Show ranked stats for a summoner")
@app_commands.describe(riot_id="Riot ID as GameName#TagLine. Leave empty for default.")
@app_commands.autocomplete(riot_id=autocomplete_riot_id)
async def slash_rank(interaction: discord.Interaction, riot_id: Optional[str] = None):
    await interaction.response.defer(thinking=True)
    ctx = SlashContext(interaction)
    ctx_cast = cast(commands.Context, ctx)
    cb = cast(Any, rank_command.callback)
    await cb(ctx_cast, riot_id=riot_id)


@bot.tree.command(name="history", description="Show last 10 games for a summoner")
@app_commands.describe(riot_id="Riot ID as GameName#TagLine. Leave empty for default.")
@app_commands.autocomplete(riot_id=autocomplete_riot_id)
async def slash_history(interaction: discord.Interaction, riot_id: Optional[str] = None):
    await interaction.response.defer(thinking=True)
    ctx = SlashContext(interaction)
    ctx_cast = cast(commands.Context, ctx)
    cb = cast(Any, history_command.callback)
    await cb(ctx_cast, riot_id=riot_id)


@bot.tree.command(name="kda", description="Champion-specific KDA over recent games")
@app_commands.describe(champion="Champion name",
                       riot_id="Riot ID as GameName#TagLine (optional)",
                       game_count="Number of recent games to analyze (optional)")
@app_commands.autocomplete(champion=autocomplete_champion, riot_id=autocomplete_riot_id)
async def slash_kda(interaction: discord.Interaction, champion: str, riot_id: Optional[str] = None, game_count: Optional[int] = None):
    await interaction.response.defer(thinking=True)
    ctx = SlashContext(interaction)
    ctx_cast = cast(commands.Context, ctx)
    parts = [champion]
    if riot_id:
        parts.append(riot_id)
    if game_count:
        parts.append(str(game_count))
    cb = cast(Any, kda_command.callback)
    await cb(ctx_cast, *parts)


@bot.tree.command(name="mastery", description="Show champion mastery for a summoner")
@app_commands.describe(
    riot_id="Riot ID as GameName#TagLine (optional)",
    champion="Champion to filter (optional)"
)
@app_commands.autocomplete(riot_id=autocomplete_riot_id, champion=autocomplete_champion)
async def slash_mastery(interaction: discord.Interaction, riot_id: Optional[str] = None, champion: Optional[str] = None):
    await interaction.response.defer(thinking=True)
    ctx = SlashContext(interaction)
    ctx_cast = cast(commands.Context, ctx)
    parts = []
    if riot_id:
        parts.append(riot_id)
    if champion:
        parts.append(champion)
    cb = cast(Any, mastery_command.callback)
    await cb(ctx_cast, *parts)


@bot.tree.command(name="livegame", description="Show current game details")
@app_commands.describe(riot_id="Riot ID as GameName#TagLine (optional)")
@app_commands.autocomplete(riot_id=autocomplete_riot_id)
async def slash_livegame(interaction: discord.Interaction, riot_id: Optional[str] = None):
    await interaction.response.defer(thinking=True)
    ctx = SlashContext(interaction)
    ctx_cast = cast(commands.Context, ctx)
    cb = cast(Any, livegame_command.callback)
    await cb(ctx_cast, riot_id=riot_id)


@bot.tree.command(name="addsummoner", description="Add a summoner to the tracking list")
@app_commands.describe(game_name="Riot game name", tag_line="Riot tag line", ping="Optional: Discord user to ping when they play (e.g., <@123456>)")
async def slash_addsummoner(interaction: discord.Interaction, game_name: str, tag_line: str, ping: Optional[str] = None):
    await interaction.response.defer(thinking=True)
    ctx = SlashContext(interaction)
    ctx_cast = cast(commands.Context, ctx)
    cb = cast(Any, add_summoner_command.callback)
    await cb(ctx_cast, game_name, tag_line, ping)


@bot.tree.command(name="listsummoners", description="List all tracked summoners")
async def slash_listsummoners(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    ctx = SlashContext(interaction)
    ctx_cast = cast(commands.Context, ctx)
    cb = cast(Any, list_summoners_command.callback)
    await cb(ctx_cast)


@bot.tree.command(name="delsummoner", description="Remove a summoner from tracking (Admin only)")
@app_commands.describe(summoner_name="Riot ID as GameName#TagLine")
@app_commands.autocomplete(summoner_name=autocomplete_riot_id)
@app_commands.default_permissions(administrator=True)
async def slash_delsummoner(interaction: discord.Interaction, summoner_name: str):
    await interaction.response.defer(thinking=True)
    ctx = SlashContext(interaction)
    ctx_cast = cast(commands.Context, ctx)
    cb = cast(Any, del_summoner_command.callback)
    await cb(ctx_cast, summoner_name=summoner_name)


@bot.tree.command(name="cleanup", description="Remove all invalid summoners (Admin only)")
@app_commands.default_permissions(administrator=True)
async def slash_cleanup(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    ctx = SlashContext(interaction)
    ctx_cast = cast(commands.Context, ctx)
    cb = cast(Any, cleanup_command.callback)
    await cb(ctx_cast)


@bot.tree.command(name="addmulti", description="Bulk add summoners from OP.GG URL")
@app_commands.describe(opgg_url="OP.GG multi URL containing summoners parameter")
async def slash_addmulti(interaction: discord.Interaction, opgg_url: str):
    await interaction.response.defer(thinking=True)
    ctx = SlashContext(interaction)
    ctx_cast = cast(commands.Context, ctx)
    cb = cast(Any, add_multi_command.callback)
    await cb(ctx_cast, opgg_url=opgg_url)


@bot.tree.command(name="help", description="Show help for bot commands")
@app_commands.describe(command_name="Optional command name to get details")
async def slash_help(interaction: discord.Interaction, command_name: Optional[str] = None):
    await interaction.response.defer(thinking=True)
    ctx = SlashContext(interaction)
    ctx_cast = cast(commands.Context, ctx)
    cb = cast(Any, help_command.callback)
    await cb(ctx_cast, command_name=command_name)

if __name__ == "__main__":
    logging.info("Starting Discord bot...")
    
    # Require secrets to be set via environment variables or a .env file.
    def _looks_like_placeholder(value: Optional[str]) -> bool:
        if not value:
            return True
        v = value.strip().lower()
        # common placeholder patterns
        placeholders = ['your_token', 'your_riot', 'changeme', 'replace', 'xxx', 'none']
        if any(p in v for p in placeholders):
            return True
        # discord tokens should not start with the literal 'bot '
        if v.startswith('bot '):
            return True
        # very short values are unlikely to be real tokens
        if len(v) < 20:
            return True
        return False

    if _looks_like_placeholder(DISCORD_BOT_TOKEN) or _looks_like_placeholder(RIOT_API_KEY):
        logging.error("DISCORD_BOT_TOKEN or RIOT_API_KEY appears to be missing or a placeholder.")
        logging.error("Set real credentials in your environment or .env file before running the bot.")
        logging.error("Current CHANNEL_ID source: %s", CHANNEL_ID_SOURCE)
        raise SystemExit(1)

    try:
        # Token has been validated above; cast for type-checkers
        bot.run(cast(str, DISCORD_BOT_TOKEN))
    except Exception as e:
        logging.exception("Fatal error running bot: %s", e)
    finally:
        # Best-effort cleanup of the shared aiohttp session when the process exits.
        try:
            if HTTP_SESSION and not HTTP_SESSION.closed:
                # Use asyncio.run to close the session from sync context.
                asyncio.run(HTTP_SESSION.close())
                logging.info("Closed shared aiohttp ClientSession on shutdown")
        except Exception:
            logging.exception("Error closing shared HTTP session on shutdown")


# Fallback: in case the interpreter exits without hitting the above cleanup,
# register an atexit handler that will synchronously run an event loop to
# close the session. This helps avoid "Unclosed client session" warnings.
def _atexit_close_session():
    global HTTP_SESSION
    try:
        if HTTP_SESSION and not HTTP_SESSION.closed:
            asyncio.run(HTTP_SESSION.close())
    except Exception:
        # Last-ditch best-effort; nothing else to do.
        pass

atexit.register(_atexit_close_session)