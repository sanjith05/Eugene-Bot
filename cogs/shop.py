from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

from utils import database as db
from utils import embeds


def _format_shop(shop: dict) -> str:
    colors = shop.get("color_roles", [])
    specials = shop.get("specials", [])
    lines: List[str] = []
    if colors:
        lines.append("Color Roles:")
        for it in colors:
            lines.append(f"• {it.get('name')} — {it.get('price')} coins")
    if specials:
        if lines:
            lines.append("")
        lines.append("Special Roles:")
        for it in specials:
            lines.append(f"• {it.get('name')} — {it.get('price')} coins")
    return "\n".join(lines) or "No items yet."


class Shop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="shop", description="View the role shop")
    async def shop(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        shop = await db.get_shop()
        user = await db.get_user(interaction.user.id)
        coins = int(user.get("coins", 0))
        desc = _format_shop(shop)
        await interaction.edit_original_response(embed=embeds.base(f"Shop · Your coins: {coins}", desc))

    @app_commands.command(name="shop_buy", description="Buy a role from the shop")
    @app_commands.describe(kind="Type of item", name="Role name exactly as in server")
    @app_commands.choices(kind=[
        app_commands.Choice(name="color", value="color_roles"),
        app_commands.Choice(name="special", value="specials"),
    ])
    async def shop_buy(self, interaction: discord.Interaction, kind: app_commands.Choice[str], name: str):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.edit_original_response(embed=embeds.error("Use in a server."))
            return
        shop = await db.get_shop()
        items = shop.get(kind.value, [])
        target = None
        for it in items:
            if it.get("name").lower() == name.lower():
                target = it
                break
        if not target:
            await interaction.edit_original_response(embed=embeds.warn("Item not found."))
            return
        price = int(target.get("price", 0))
        user = await db.get_user(interaction.user.id)
        coins = int(user.get("coins", 0))
        if coins < price:
            await interaction.edit_original_response(embed=embeds.warn("Not enough coins."))
            return
        role = discord.utils.get(interaction.guild.roles, name=target.get("name"))
        if not role:
            await interaction.edit_original_response(embed=embeds.error("Role not found in server."))
            return
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.edit_original_response(embed=embeds.error("I need Manage Roles permission."))
            return
        member = interaction.guild.get_member(interaction.user.id)
        try:
            await member.add_roles(role, reason="Shop purchase")
        except discord.Forbidden:
            await interaction.edit_original_response(embed=embeds.error("Cannot assign role (role hierarchy)."))
            return
        user["coins"] = coins - price
        await db.set_user(interaction.user.id, user)
        await interaction.edit_original_response(embed=embeds.success(f"Purchased {role.name} for {price} coins. Balance: {user['coins']}"))

    @app_commands.command(name="shop_add_role", description="Admin: add a color role to the shop")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shop_add_role(self, interaction: discord.Interaction, role: discord.Role, price: int):
        await interaction.response.defer(ephemeral=True)
        shop = await db.get_shop()
        colors = list(shop.get("color_roles", []))
        # Update if exists
        for it in colors:
            if it.get("name") == role.name:
                it["price"] = int(price)
                break
        else:
            colors.append({"name": role.name, "price": int(price)})
        shop["color_roles"] = colors
        await db.set_shop(shop)
        await interaction.edit_original_response(embed=embeds.success(f"Added/updated color role {role.name} @ {price} coins."))

    @app_commands.command(name="shop_add_special", description="Admin: add a special role to the shop")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shop_add_special(self, interaction: discord.Interaction, role: discord.Role, price: int):
        await interaction.response.defer(ephemeral=True)
        shop = await db.get_shop()
        specials = list(shop.get("specials", []))
        for it in specials:
            if it.get("name") == role.name:
                it["price"] = int(price)
                break
        else:
            specials.append({"name": role.name, "price": int(price)})
        shop["specials"] = specials
        await db.set_shop(shop)
        await interaction.edit_original_response(embed=embeds.success(f"Added/updated special role {role.name} @ {price} coins."))

    @app_commands.command(name="coins_grant", description="Admin: grant coins to a user")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def coins_grant(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)
        u = await db.get_user(user.id)
        u["coins"] = int(u.get("coins", 0)) + int(amount)
        await db.set_user(user.id, u)
        await interaction.edit_original_response(embed=embeds.success(f"Granted {amount} coins to {user.display_name}. New balance: {u['coins']}"))


async def setup(bot: commands.Bot):
    await bot.add_cog(Shop(bot))
