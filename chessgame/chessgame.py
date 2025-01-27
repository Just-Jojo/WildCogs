"""cog to play chess in discord"""
import io
import asyncio
from typing import Dict

import discord
import jsonpickle
from redbot.core import Config, commands
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

from .game import Game, start_help_text
from copy import copy
from contextlib import suppress

# type hints
Games = Dict[str, Game]


class ChessGame(commands.Cog):
    """Cog to Play chess!"""

    _fifty_moves = 'Fifty moves'
    _threefold_repetition = 'Threefold repetition'

    def __init__(self, bot):
        super().__init__()

        self._config = Config.get_conf(
            self, identifier=51314929031968350236701571200827144869558993811)
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False
        permissions = ctx.channel.permissions_for(ctx.me)
        return all([permissions.embed_links, permissions.add_reactions])

    async def _get_games(self, channel) -> Games:
        games_json = await self._config.channel(channel).games()
        if games_json:
            games = jsonpickle.decode(games_json)
            return games
        else:
            return None

    async def _set_games(self, channel, games):
        games_json = jsonpickle.encode(games)
        await self._config.channel(channel).games.set(games_json)

    @commands.group()
    async def chess(self, ctx: commands.Context):
        """Manage chess games"""

    @chess.command(name='start', autohelp=False, help=start_help_text())
    async def start_game(self, ctx: commands.Context,
                         other_player: discord.Member,
                         game_name: str = None, game_type: str = None):
        """Sub command to start a new game"""

        # get games config
        games = await self._get_games(ctx.channel)
        if not games:
            games = {}

        player_black = ctx.author
        player_white = other_player
        if player_black == player_white:
            return await ctx.send("You cannot play chess with yourself")

        # init game_name if not provided
        if not game_name:
            game_name = f'game'

        # make game_name unique if already exists
        count = 0
        suffix = ''
        while game_name + suffix in games.keys():
            count += 1
            suffix = f'{count}'

        game_name += suffix

        embed: discord.Embed = discord.Embed(
            title="Chess",
            description=f"Game: {game_name}",
            colour=await ctx.embed_colour()
        )

        try:
            game = Game(player_black.id, player_white.id, game_type)
        except ValueError:
            embed.add_field(name='Invalid Game Type:', value=game_type)
            await ctx.send(embed=embed)
            return

        games[game_name] = game

        await self._set_games(ctx.channel, games)

        embed.add_field(name="New Game",
                        value=f"<@{player_white.id}>'s (White's) turn is first",
                        inline=False)

        await self._display_board(ctx, embed, game)

    async def _display_board(self, ctx: commands.Context, embed: discord.Embed, game: Game):
        """Displays the game board"""
        board_image = io.BytesIO(game.get_board_image())
        embed.set_image(url="attachment://board.png")
        await ctx.send(embed=embed, file=discord.File(board_image, 'board.png'))

    @chess.command(name='list', autohelp=False)
    async def list_games(self, ctx: commands.Context):
        """List all available games"""
        no_games = True

        max_len = 1000

        embed: discord.Embed = discord.Embed(
            title="Chess",
            description="Chess Game List",
            colour=await ctx.embed_colour()
        )

        total_len = len(embed.title) + len(embed.description)

        for channel in ctx.guild.channels:
            games = await self._get_games(channel)
            count = 0
            output = ''

            if not games:
                continue
            no_games = False

            for game_name, game in games.items():
                player_white = ctx.guild.get_member(game.player_white_id)
                player_black = ctx.guild.get_member(game.player_black_id)

                count += 1
                current_game = f'\n** Game: #{count}** - __{game_name}__\n' \
                    f'```Black: {player_black.name}\n' \
                    f'White: {player_white.name}\n' \
                    f'Total Moves: {game.total_moves}\n' \
                    f'Type: {game.type}```'

                current_game_len = len(current_game)

                # send it now if we hit our limit
                if total_len + current_game_len > max_len:
                    embed.add_field(
                        name=f'Channel - {channel}',
                        value='__List of games:__' + output,
                        inline=False)
                    output = current_game
                    total_len = current_game_len

                    await ctx.send(embed=embed)
                    embed: discord.Embed = discord.Embed()

                    embed.title = "Chess"
                    embed.description = "Chess Game List - Continued"
                else:
                    output += current_game
                    total_len += current_game_len

            # add field for remaining
            embed.add_field(
                name=f'Channel - {channel}',
                value='__List of games:__' + output,
                inline=False)

        if no_games:
            embed.add_field(name="No Games Available",
                            value='You can start a new game with [p]chess start')
        await ctx.send(embed=embed)

    @chess.command(name='move', autohelp=False)
    async def move_piece(self, ctx: commands.Context, game_name: str, move: str):
        """Move the next game piece, using Standard Algebraic Notation"""

        embed: discord.Embed = discord.Embed(
            title="Chess",
            description=f"Game: {game_name}",
            colour=await ctx.embed_colour(),
        )

        try:
            games = await self._get_games(ctx.channel)
            game = games[game_name]
        except KeyError:
            # this game doesn't exist
            embed.add_field(name="Game does not exist",
                            value="This game doesn't appear to exist, please check the "
                            "game list to ensure you are entering it correctly")
            await ctx.send(embed=embed)
            return

        embed.add_field(name="Type:", value=game.type, inline=False)

        player_white = ctx.guild.get_member(game.player_white_id)
        player_black = ctx.guild.get_member(game.player_black_id)

        turn_color, player_turn, player_next = game.order
        # convert ids to members
        if player_turn == game.player_white_id:
            player_turn = player_white
            player_next = player_black
        else:
            player_turn = player_black
            player_next = player_white

        if player_turn == ctx.author:
            # it is their turn
            try:
                is_game_over, value_move = game.move_piece(move)
            except ValueError:
                embed.add_field(name="Invalid Move Taken!",
                                value=f"'{move}' isn't a valid move, try again.")
                await ctx.send(embed=embed)
                return

            name_move = f"Move: {game.total_moves} - " \
                f"{player_turn.name}'s ({turn_color}'s) Turn"

            if is_game_over:
                del games[game_name]
                embed.add_field(
                    name="Game Over!",
                    value="Match is over! Start a new game if you want to play again.")

            embed.add_field(name=name_move,
                            value=value_move)

            # show if can claim draw
            if game.can_claim_draw:

                if game.can_claim_fifty_moves:
                    fifty_moves = f'\n"{self._fifty_moves }"'
                else:
                    fifty_moves = ''

                if game.can_claim_threefold_repetition:
                    threefold_repetition = f'\n"{self._threefold_repetition}"'
                else:
                    threefold_repetition = ''

                embed.add_field(
                    name='Draw can be claimed',
                    value='To end this game now use "[p]chess draw claim" with:' +
                    fifty_moves +
                    threefold_repetition)

            await self._set_games(ctx.channel, games)

            await self._display_board(ctx, embed, game)
        elif player_next == ctx.author:
            # not their turn yet
            embed.add_field(name=f"{player_next.name} - not your turn",
                            value=f"{player_next.name} it doesn't look like its your turn yet! "
                            f"<@{player_turn.id}> ({turn_color}) still needs to make a move "
                            "before you can.")
            await ctx.send(embed=embed)
        else:
            # not a player
            embed.add_field(name=f"{ctx.author.name} - not a player",
                            value=f"{ctx.author.name} you are not part of this game!\n"
                            f"Only {player_black.name} (Black) and {player_white.name} ' \
                            '(White) are able to play in this game")
            await ctx.send(embed=embed)

    @chess.command(name="resign")
    async def resign(self, ctx: commands.Context, game_name: str, confirm: bool = False):
        """Resign the game"""
        embed = discord.Embed(
            title="Chess",
            description=f"Game: {game_name}",
            colour=await ctx.embed_colour(),
        )

        try:
            games = await self._get_games(ctx.channel)
            game = games[game_name]
        except KeyError:
            embed.add_field(
                name="Game does not exist",
                value=(
                    "This game does not appear to exist, please check "
                    "the game list to ensure you are entering it correctly"
                )
            )
            return await ctx.send(embed=embed)
        player_white, player_black = [
            ctx.guild.get_member(_id)
            for _id in (
                game.player_white_id, game.player_black_id
            )
        ]
        if ctx.author not in (player_white, player_black):
            embed.add_field(
                name=f"{ctx.author.name} - Not player",
                value=(
                    f"{ctx.author.name} you are not a part of the game!\n"
                    f"Only {player_black.name} (Black) and {player_white.name} (White) "
                    "are able to play this game"
                ),
            )
            return await ctx.send(embed=embed)
        msg = None
        if not confirm:
            embed.add_field(name="Please confirm.", value="Would you like to resign?")
            msg = await ctx.send(embed=embed)
            start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(msg, user=ctx.author)
            try:
                await ctx.bot.wait_for("reaction_add", check=pred)
                if not pred.result:
                    embed.add_field(
                        name="Cancelled",
                        value=f"{ctx.author.name} has not confirmed a resignation"
                    )
                    return await msg.edit(embed=embed)
            except asyncio.TimeoutError:
                embed.add_field(name="Timed out", value=f"{ctx.author.name} did not respond.")
                return await msg.edit(embed=embed)
        if ctx.author == player_white:
            embed.add_field(
                name=f"{player_white.name} resigned",
                value=(
                    f"Player {player_white.name} (White) has resigned!\n"
                    f"Player {player_black.name} (Black) has won!"
                ),
            )
        elif ctx.author == player_black:
            embed.add_field(
                name=f"{player_black.name} resigned",
                value=(
                    f"Player {player_black.name} (Black) has resigned!\n"
                    f"Player {player_white.name} (White) has won!"
                ),
                inline=False,
            )
        del games[game_name]
        if msg:
            with suppress(discord.NotFound):
                await msg.edit(embed=embed)
        else:
            await ctx.send(embed=embed)
        await self._set_games(ctx.channel, games)

    @chess.group(name='draw')
    async def draw(self, ctx: commands.Context):
        """Draw related commands"""

    @draw.command(name='claim', autohelp=False)
    async def claim_draw(self, ctx: commands.Context, game_name: str, claim_type: str):
        """If valid claim made to draw the game will end with no victor"""

        embed: discord.Embed = discord.Embed(
            title="Chess",
            description="Claim Draw",
        )

        try:
            games = await self._get_games(ctx.channel)
            game = games[game_name]
        except KeyError:
            embed.add_field(name="Game does not exist",
                            value="This game doesn't appear to exist, please check the "
                            "game list to ensure you are entering it correctly")
            await ctx.send(embed=embed)
            return

        if self._fifty_moves == claim_type and game.can_claim_fifty_moves:
            embed.add_field(
                name=f'Draw! - {claim_type}',
                value='There are been no captures or pawns moved in the last 50 moves'
            )
            del games[game_name]
            await self._set_games(ctx.channel, games)
        elif self._threefold_repetition == claim_type and game.can_claim_threefold_repetition:
            embed.add_field(
                name=f'Draw! - {claim_type}',
                value='Position has occured five times'
            )
            del games[game_name]
            await self._set_games(ctx.channel, games)
        else:
            embed.add_field(
                name=claim_type,
                value=f'Unable to claim {claim_type}\n'
                f'{claim_type} is not a valid reason, the game is not drawn.'
            )

        await ctx.send(embed=embed)

    @draw.group(name='byagreement', autohelp=False)
    async def by_agreement(self, ctx: commands.Context, game_name: str):
        """Offer draw by agreement"""

        embed: discord.Embed = discord.Embed(
            title="Chess",
            description="Offer Draw"
        )

        try:
            games = await self._get_games(ctx.channel)
            game = games[game_name]
        except KeyError:
            embed.add_field(name="Game does not exist",
                            value="This game doesn't appear to exist, please check the "
                            "game list to ensure you are entering it correctly")
            await ctx.send(embed=embed)
            return

        # identify the other player to mention
        if ctx.author.id == game.player_black_id:
            other_player = game.player_white_id
        elif ctx.author.id == game.player_white_id:
            other_player = game.player_black_id
        else:  # not part of this game
            embed.add_field(
                name="You are not part of this game",
                value="You are not able to offer a draw if you are not one of the players.")
            await ctx.send(embed=embed)
            return

        embed.add_field(
            name=f"{ctx.author.name} has offered a draw",
            value=f"<@{other_player}> respond below:")

        message = await ctx.send(embed=embed)

        # yes / no reaction options
        start_adding_reactions(message, ReactionPredicate.YES_OR_NO_EMOJIS)

        pred = ReactionPredicate.yes_or_no(
            message,
            ctx.guild.get_member(game.player_white_id))
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=30)
            if pred.result is True:
                embed.add_field(
                    name="Response:",
                    value="Draw accepted!")
                del games[game_name]
                await self._set_games(ctx.channel, games)
            else:
                embed.add_field(
                    name="Response:",
                    value="Draw declined!")
        except asyncio.TimeoutError:
            embed.add_field(
                name="Timed out:",
                value=f"<@{other_player}> did not respond in time.")

        await message.edit(embed=embed)
        await message.clear_reactions()
