"""chess cog init"""
from .chessgame import ChessGame


async def setup(bot):
    """add cog to bot collection"""
    await bot.add_cog(ChessGame(bot))
