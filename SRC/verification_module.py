import secrets
import time
import asyncio
import discord
from discord import app_commands, ui
from configuration_module import get_guild_config, save_config, is_admin, safe_join_items

# Short-term cache for verification sessions
# Key: (guild_id, user_id) -> Value: (correct_code_string, timestamp)
active_verification_codes = {}

async def send_admin_notification(guild: discord.Guild, embed: discord.Embed):
    cfg = get_guild_config(guild.id)
    sent = False
    
    # 1 & 2. Aggregate target channel IDs (Precedence: verification_log -> global_log -> warning_log -> admin_channel)
    # Deduplicate IDs to avoid N+1 API calls if the same channel is configured for multiple log settings
    target_ids = []
    for key in ["verification_log_channel_id", "global_log_channel_id", "warning_log_channel_id", "channel_id"]:
        val = cfg.get(key)
        if val and val not in target_ids:
            target_ids.append(val)
            
    for ch_id in target_ids:
        try:
            ch = guild.get_channel(ch_id) or await guild.fetch_channel(ch_id)
            if ch:
                await ch.send(embed=embed)
                sent = True
                break
        except Exception:
            pass
            
    # System channel
    if guild.system_channel and not sent:
        try:
            await guild.system_channel.send(embed=embed)
            sent = True
        except Exception:
            pass
            
    # DM guild owner
    if not sent and guild.owner:
        try:
            await guild.owner.send(embed=embed)
        except Exception:
            pass

async def schedule_verification_kick(member: discord.Member, timeout: int):
    await asyncio.sleep(timeout)
    try:
        guild = member.guild
        cfg = get_guild_config(guild.id)
        if not cfg.get("verification_enabled", False):
            return
        current_timeout = cfg.get("verification_timeout", 0)
        if current_timeout <= 0:
            return
            
        try:
            fresh_member = guild.get_member(member.id) or await guild.fetch_member(member.id)
        except discord.NotFound:
            return
            
        if not fresh_member:
            return
            
        verified = False
        verified_role_ids = cfg.get("verification_verified_role_ids") or []
        single_verified_role = cfg.get("verification_verified_role_id")
        if single_verified_role and single_verified_role not in verified_role_ids:
            verified_role_ids = [single_verified_role] + verified_role_ids
            
        unverified_role_id = cfg.get("verification_unverified_role_id")
        
        # If verified roles exist, check if user has any of them
        if verified_role_ids:
            if any(role.id in verified_role_ids for role in fresh_member.roles):
                verified = True
                
        # If unverified role exists, check if user no longer has it
        if unverified_role_id and not verified:
            if fresh_member.get_role(unverified_role_id) is None:
                verified = True
                
        if not verified:
            try:
                await fresh_member.kick(reason=f"Verification timeout of {timeout}s exceeded.")
                log_ch_id = cfg.get("verification_log_channel_id") or cfg.get("global_log_channel_id")
                if log_ch_id:
                    try:
                        ch = guild.get_channel(log_ch_id) or await guild.fetch_channel(log_ch_id)
                        if ch:
                            import datetime
                            embed = discord.Embed(
                                title="Verification Timeout Kick",
                                description=f"Kicked {fresh_member.name} ({fresh_member.id}) - Verification timeout of {timeout}s exceeded.",
                                color=discord.Color.red(),
                                timestamp=datetime.datetime.utcnow()
                            )
                            embed.set_footer(text="Moderator: System")
                            await ch.send(embed=embed)
                    except Exception:
                        pass
            except discord.Forbidden as ex:
                print(f"[ERROR] Permission error: Nebot lacks Kick Members permission or target role is too high to kick user {fresh_member.name} ({fresh_member.id}) in guild {guild.name} ({guild.id}): {ex}")
                embed = discord.Embed(
                    title="[WARNING] Verification Timeout Kick Failed",
                    description=(
                        f"The bot failed to kick **{fresh_member.name}** for verification timeout "
                        f"because it lacks the Kick Members permission or the user's highest role is above the bot's."
                    ),
                    color=discord.Color.red()
                )
                await send_admin_notification(guild, embed)
            except Exception as ex:
                print(f"[ERROR] Failed to kick user {fresh_member.name} ({fresh_member.id}) in guild {guild.name} ({guild.id}): {ex}")
    except Exception:
        pass

class VerificationSelect(ui.Select):
    def __init__(self, correct_code: str, options_pool: list[str]):
        options = [discord.SelectOption(label=code, value=code) for code in options_pool]
        super().__init__(placeholder="Select Code...", options=options, custom_id="verification_select")
        self.correct_code = correct_code

    async def callback(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        user_id = interaction.user.id
        
        # Flush the session token immediately to prevent double click/brute-force
        stored_data = active_verification_codes.pop((guild_id, user_id), None)
        if not stored_data:
            await interaction.response.edit_message(
                content="Verification session expired or not found. Please click 'Get your code' to try again.",
                embed=None,
                view=None
            )
            return

        correct_code, created_at = stored_data
        
        # Check expiration (5 minutes / 300 seconds)
        if time.time() - created_at > 300:
            await interaction.response.edit_message(
                content="Verification session expired. Please click 'Get your code' to try again.",
                embed=None,
                view=None
            )
            return

        selected_code = self.values[0]
        
        # Strict string comparison to prevent drop-off zero omissions
        if selected_code == correct_code:
            cfg = get_guild_config(guild_id)
            verified_role_ids = cfg.get("verification_verified_role_ids") or []
            single_verified_role = cfg.get("verification_verified_role_id")
            if single_verified_role and single_verified_role not in verified_role_ids:
                verified_role_ids = [single_verified_role] + verified_role_ids
            unverified_role_id = cfg.get("verification_unverified_role_id")
            
            member = interaction.user
            roles_to_add = []
            roles_to_remove = []
            
            for rid in verified_role_ids:
                if rid:
                    v_role = interaction.guild.get_role(rid)
                    if v_role:
                        roles_to_add.append(v_role)
            
            if unverified_role_id:
                uv_role = interaction.guild.get_role(unverified_role_id)
                if uv_role:
                    roles_to_remove.append(uv_role)
            
            # Atomic role mutation
            new_roles = [r for r in member.roles if r not in roles_to_remove]
            for r in roles_to_add:
                if r not in new_roles:
                    new_roles.append(r)
            
            # Proactive hierarchy verification check
            bot_member = interaction.guild.me
            if not bot_member:
                try:
                    bot_member = await interaction.guild.fetch_member(interaction.client.user.id)
                except Exception:
                    pass
            
            role_hierarchy_error = False
            if bot_member:
                for r in roles_to_add + roles_to_remove:
                    if r.position >= bot_member.top_role.position:
                        role_hierarchy_error = True
                        break
            
            if role_hierarchy_error:
                print(f"[ERROR] Permission error: Nebot cannot modify roles for user {member.name} ({member.id}) in guild {interaction.guild.name} ({interaction.guild.id}) due to role hierarchy.")
                embed = discord.Embed(
                    title="[WARNING] Verification System Configuration Error",
                    description=(
                        f"The bot failed to modify roles for **{member.name}** because its highest "
                        f"hierarchical role sits below or equal to the configured Verified/Unverified roles in the guild's settings."
                    ),
                    color=discord.Color.red()
                )
                await send_admin_notification(interaction.guild, embed)
                await interaction.response.edit_message(
                    content="Verification failed due to a server configuration error. Administrators have been notified.",
                    embed=None,
                    view=None
                )
                return

            try:
                await member.edit(roles=new_roles)
            except discord.Forbidden as ex:
                print(f"[ERROR] Permission error: Nebot lacks permission to edit roles for user {member.name} ({member.id}) in guild {interaction.guild.name} ({interaction.guild.id}): {ex}")
                embed = discord.Embed(
                    title="[WARNING] Verification System Configuration Error",
                    description=(
                        f"The bot failed to modify roles for **{member.name}** because its highest "
                        f"hierarchical role sits below the configured Verified/Unverified roles in the guild's settings."
                    ),
                    color=discord.Color.red()
                )
                await send_admin_notification(interaction.guild, embed)
                await interaction.response.edit_message(
                    content="Verification failed due to a server configuration error. Administrators have been notified.",
                    embed=None,
                    view=None
                )
                return
            except Exception as e:
                await interaction.response.edit_message(
                    content=f"An unexpected error occurred during role modification: {e}",
                    embed=None,
                    view=None
                )
                return
            
            # Successful verification response
            await interaction.response.edit_message(
                content="Verification successful! Welcome to the server.",
                embed=None,
                view=None
            )
            
            # Send verification log to active log channel (verification or global fallback)
            log_ch_id = cfg.get("verification_log_channel_id") or cfg.get("global_log_channel_id")
            if log_ch_id:
                try:
                    ch = interaction.guild.get_channel(log_ch_id) or await interaction.guild.fetch_channel(log_ch_id)
                    if ch:
                        await ch.send(f"User {member.mention} has been verified")
                except Exception:
                    pass
            
            # Send arrival welcome message to landing channel if configured
            landing_ch_id = cfg.get("verification_landing_channel_id")
            if landing_ch_id:
                try:
                    ch = interaction.guild.get_channel(landing_ch_id) or await interaction.guild.fetch_channel(landing_ch_id)
                    if ch:
                        await ch.send(f"Welcome to the server, {member.mention}!")
                except Exception:
                    pass
        else:
            # Incorrect code selection
            await interaction.response.edit_message(
                content="Verification failed. Incorrect code selected. Please click 'Get your code' to try again with a new code generation.",
                embed=None,
                view=None
            )

class VerificationSelectView(ui.View):
    def __init__(self, correct_code: str, options_pool: list[str]):
        super().__init__(timeout=300)
        self.add_item(VerificationSelect(correct_code, options_pool))

class VerificationGateView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Get your code", style=discord.ButtonStyle.primary, custom_id="verification_gate:get_code")
    async def get_code(self, interaction: discord.Interaction, button: ui.Button):
        guild_id = interaction.guild_id
        user_id = interaction.user.id
        
        cfg = get_guild_config(guild_id)
        if not cfg.get("verification_enabled", False):
            await interaction.response.send_message(
                "The verification system is currently disabled on this server.",
                ephemeral=True
            )
            return

        # Generate correct 4-digit code (preserving leading zeros)
        correct_code = f"{secrets.randbelow(10000):04d}"
        
        # Generate 4 unique incorrect 4-digit codes
        incorrect_codes = set()
        while len(incorrect_codes) < 4:
            code = f"{secrets.randbelow(10000):04d}"
            if code != correct_code:
                incorrect_codes.add(code)
                
        # Cache correct code session
        active_verification_codes[(guild_id, user_id)] = (correct_code, time.time())
        
        # Shuffle correct and incorrect options
        options_pool = [correct_code] + list(incorrect_codes)
        secrets.SystemRandom().shuffle(options_pool)
        
        embed = discord.Embed(
            title="Verification Security Screening",
            description=f"Please Verify by Selecting '{correct_code}' at the selector menu",
            color=discord.Color.blue()
        )
        
        view = VerificationSelectView(correct_code, options_pool)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class VerificationTimeoutModal(ui.Modal):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        super().__init__(title="Verification Timeout Settings")
        
        cfg = get_guild_config(guild_id)
        current_timeout = cfg.get("verification_timeout", 0)
        
        self.input = ui.TextInput(
            label="Timeout in Seconds (0 to disable)",
            default=str(current_timeout) if current_timeout else "0",
            placeholder="e.g. 300 for 5 minutes, 0 to disable",
            required=True
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.input.value.strip())
            if val < 0:
                raise ValueError()
        except ValueError:
            return await interaction.response.send_message("Timeout must be a non-negative integer.", ephemeral=True)
            
        cfg = get_guild_config(self.guild_id)
        cfg["verification_timeout"] = val
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated verification timeout to {val} seconds")
        dashboard = VerificationConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(embed=embed, view=dashboard)

class VerificationConfigDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        enabled = cfg.get("verification_enabled", False)
        
        unverified_role_id = cfg.get("verification_unverified_role_id")
        unverified_role_str = f"<@&{unverified_role_id}>" if unverified_role_id else "@everyone"
        
        verified_role_ids = cfg.get("verification_verified_role_ids") or []
        single_verified_role = cfg.get("verification_verified_role_id")
        if single_verified_role and single_verified_role not in verified_role_ids:
            verified_role_ids = [single_verified_role] + verified_role_ids
            
        verified_role_str = safe_join_items([f"<@&{rid}>" for rid in verified_role_ids])
        
        channel_id = cfg.get("verification_channel_id")
        channel_str = f"<#{channel_id}>" if channel_id else "Not Set"
        
        landing_id = cfg.get("verification_landing_channel_id")
        landing_str = f"<#{landing_id}>" if landing_id else "Disabled"
        
        timeout = cfg.get("verification_timeout", 0)
        timeout_str = f"{timeout} seconds" if timeout else "Disabled"
        
        embed = discord.Embed(
            title="Nebot Module: Verification System",
            description="Configure anti-bot gateway parameters, role shifts, and permission guidelines.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Status", value="[ENABLED]" if enabled else "[DISABLED]", inline=True)
        embed.add_field(name="Unverified Role", value=unverified_role_str, inline=True)
        embed.add_field(name="Verified Roles", value=verified_role_str, inline=True)
        embed.add_field(name="Verification Channel", value=channel_str, inline=True)
        embed.add_field(name="Landing Channel", value=landing_str, inline=True)
        embed.add_field(name="Verification Timeout", value=timeout_str, inline=True)
        
        return embed

    @ui.button(label="Toggle Verification", style=discord.ButtonStyle.primary, row=0)
    async def toggle_verification(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["verification_enabled"] = not cfg.get("verification_enabled", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled Verification module state to `{'enabled' if cfg['verification_enabled'] else 'disabled'}`")
        await self.refresh(interaction)

    @ui.button(label="Set Roles", style=discord.ButtonStyle.secondary, row=0)
    async def set_roles(self, interaction: discord.Interaction, button: ui.Button):
        view = VerificationRolesView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Set Channels", style=discord.ButtonStyle.secondary, row=0)
    async def set_channels(self, interaction: discord.Interaction, button: ui.Button):
        view = VerificationChannelsView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Set Timeout", style=discord.ButtonStyle.secondary, row=0)
    async def set_timeout(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(VerificationTimeoutModal(self.guild_id))

    @ui.button(label="Show Permission Guide", style=discord.ButtonStyle.success, row=1)
    async def show_guide(self, interaction: discord.Interaction, button: ui.Button):
        guide_embed = discord.Embed(
            title="Verification System Permission Guide",
            description="Follow these guidelines to structure your server permissions correctly.",
            color=discord.Color.green()
        )
        guide_embed.add_field(
            name="1. Unverified Role Settings",
            value=(
                "Default is `@everyone`, but if a custom placeholder role (e.g. `Unverified`) is used:\n"
                "• **Deny** `View Channel` access across all **MAIN** discussion channels (e.g. general, announcements).\n"
                "• **Grant** explicit `View Channel` and `Read Message History` access strictly in the designated verification channel."
            ),
            inline=False
        )
        guide_embed.add_field(
            name="2. Verified Role Settings",
            value=(
                "This is the target role (e.g. `Member`):\n"
                "• **Grant** `View Channel` access across all main community categories.\n"
                "• **Deny** `View Channel` access to the verification channel so they cannot re-access or re-trigger the gateway."
            ),
            inline=False
        )
        await interaction.response.send_message(embed=guide_embed, ephemeral=True)

    @ui.button(label="Deploy Verification Gate", style=discord.ButtonStyle.primary, row=1)
    async def deploy_gate(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        ch_id = cfg.get("verification_channel_id")
        if not ch_id:
            await interaction.response.send_message("Please configure the Verification Channel first.", ephemeral=True)
            return
            
        guild = interaction.guild
        channel = guild.get_channel(ch_id) or await guild.fetch_channel(ch_id)
        if not channel:
            await interaction.response.send_message("Configured Verification Channel not found.", ephemeral=True)
            return
            
        gate_embed = discord.Embed(
            title="Server Identity Verification",
            description="Please complete the security screening below to unlock access to the remaining community channels. Click the button to receive your unique access code.",
            color=discord.Color.blue()
        )
        
        try:
            await channel.send(embed=gate_embed, view=VerificationGateView())
            await interaction.response.send_message(f"Verification gate successfully deployed to <#{ch_id}>.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f"Failed to deploy gate: Bot lacks permissions to send messages/embeds in <#{ch_id}>.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed to deploy gate: {e}", ephemeral=True)

    @ui.button(label="Back to Modules", style=discord.ButtonStyle.danger, row=2)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        from admin_ui_module import ModuleSelectView
        view = ModuleSelectView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        from configuration_module import refresh_interaction
        await refresh_interaction(interaction, embed, view=self)

class VerificationVerifiedRolesSelect(discord.ui.RoleSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Select Verified Roles...", min_values=1, max_values=10, row=2)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        roles = self.values
        cfg = get_guild_config(self.guild_id)
        cfg["verification_verified_role_ids"] = [r.id for r in roles]
        cfg["verification_verified_role_id"] = roles[0].id if roles else None
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Verification verified roles to: {', '.join(r.name for r in roles)}")
        if self.view:
            await self.view.refresh(interaction)
        else:
            await interaction.response.send_message("Verified roles configured successfully.", ephemeral=True)

class VerificationUnverifiedRoleSelect(discord.ui.RoleSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Select Unverified Role...", min_values=1, max_values=1, row=1)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        cfg = get_guild_config(self.guild_id)
        cfg["verification_unverified_role_id"] = role.id
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Verification unverified role to @{role.name}")
        if self.view:
            await self.view.refresh(interaction)
        else:
            await interaction.response.send_message(f"Unverified role set to @{role.name}", ephemeral=True)

class VerificationRolesView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(VerificationUnverifiedRoleSelect(guild_id))
        self.add_item(VerificationVerifiedRolesSelect(guild_id))

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        unverified_role_id = cfg.get("verification_unverified_role_id")
        unverified_role_str = f"<@&{unverified_role_id}>" if unverified_role_id else "@everyone"
        
        verified_role_ids = cfg.get("verification_verified_role_ids") or []
        single_verified_role = cfg.get("verification_verified_role_id")
        if single_verified_role and single_verified_role not in verified_role_ids:
            verified_role_ids = [single_verified_role] + verified_role_ids
            
        verified_role_str = safe_join_items([f"<@&{rid}>" for rid in verified_role_ids])

        embed = discord.Embed(
            title="Verification System: Role Configuration",
            description=(
                "Configure the operational roles.\n\n"
                "**Owner Setup Instructions:**\n"
                "• **Unverified Role**: Set to `@everyone` or a custom placeholder role (e.g., `Unverified`). This role must have "
                "its permissions explicitly stripped down in server settings—specifically denying `View Channel` access across "
                "all main discussion channels, while granting explicit `View Channel` and `Read Message History` access strictly "
                "within the designated verification channel.\n\n"
                "• **Verified Roles**: Set the target role(s) granted upon completion (e.g., `Member`). These roles must be configured "
                "with `View Channel` access granted across all main community categories, while explicitly denying `View Channel` "
                "access to the verification channel to ensure verified members cannot re-access or re-trigger the gateway."
            ),
            color=discord.Color.blue()
        )
        embed.add_field(name="Unverified Role", value=unverified_role_str, inline=True)
        embed.add_field(name="Verified Roles", value=verified_role_str, inline=True)
        return embed

    @ui.button(label="Clear Unverified Role", style=discord.ButtonStyle.secondary, row=0)
    async def clear_unverified_role(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["verification_unverified_role_id"] = None
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, "Cleared Verification unverified role")
        await self.refresh(interaction)

    @ui.button(label="Clear Verified Roles", style=discord.ButtonStyle.secondary, row=0)
    async def clear_verified_roles(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["verification_verified_role_ids"] = []
        cfg["verification_verified_role_id"] = None
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, "Cleared Verification verified roles")
        await self.refresh(interaction)

    @ui.button(label="Back", style=discord.ButtonStyle.danger, row=3)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = VerificationConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(embed=embed, view=dashboard)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        from configuration_module import refresh_interaction
        await refresh_interaction(interaction, embed, view=self)

class VerificationChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Select Verification Channel...", min_values=1, max_values=1, channel_types=[discord.ChannelType.text], row=1)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        cfg = get_guild_config(self.guild_id)
        cfg["verification_channel_id"] = channel.id
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Verification channel to {channel.mention}")
        if self.view:
            await self.view.refresh(interaction)
        else:
            await interaction.response.send_message(f"Verification channel set to <#{channel.id}>", ephemeral=True)

class VerificationLandingChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Select Landing Channel...", min_values=1, max_values=1, channel_types=[discord.ChannelType.text], row=2)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        cfg = get_guild_config(self.guild_id)
        cfg["verification_landing_channel_id"] = channel.id
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Verification landing channel to {channel.mention}")
        if self.view:
            await self.view.refresh(interaction)
        else:
            await interaction.response.send_message(f"Landing channel set to <#{channel.id}>", ephemeral=True)

class VerificationLogChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Select Verification Log Channel...", min_values=1, max_values=1, channel_types=[discord.ChannelType.text], row=3)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        cfg = get_guild_config(self.guild_id)
        cfg["verification_log_channel_id"] = channel.id
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Updated Verification log channel to {channel.mention}")
        if self.view:
            await self.view.refresh(interaction)
        else:
            await interaction.response.send_message(f"Verification log channel set to <#{channel.id}>", ephemeral=True)

class VerificationChannelsView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(VerificationChannelSelect(guild_id))
        self.add_item(VerificationLandingChannelSelect(guild_id))
        self.add_item(VerificationLogChannelSelect(guild_id))

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        channel_id = cfg.get("verification_channel_id")
        channel_str = f"<#{channel_id}>" if channel_id else "Not Set"
        
        landing_id = cfg.get("verification_landing_channel_id")
        landing_str = f"<#{landing_id}>" if landing_id else "Disabled"

        log_id = cfg.get("verification_log_channel_id")
        global_log_id = cfg.get("global_log_channel_id")
        if log_id:
            log_str = f"<#{log_id}>"
        elif global_log_id:
            log_str = f"<#{global_log_id}> (Global fallback)"
        else:
            log_str = "None"

        embed = discord.Embed(
            title="Verification System: Channel Configuration",
            description=(
                "Configure the channels where users verify and arrive.\n\n"
                "• **Verification Channel**: The specific text channel where the gateway message lives.\n"
                "• **Landing Channel**: Optional destination where verified members receive an automated arrival message.\n"
                "• **Verification Log Channel**: Specific log channel for verification events. Falls back to global log channel if none is set."
            ),
            color=discord.Color.blue()
        )
        embed.add_field(name="Verification Channel", value=channel_str, inline=True)
        embed.add_field(name="Landing Channel", value=landing_str, inline=True)
        embed.add_field(name="Verification Log Channel", value=log_str, inline=True)
        return embed

    @ui.button(label="Clear Verification Channel", style=discord.ButtonStyle.secondary, row=0)
    async def clear_verification_channel(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["verification_channel_id"] = None
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, "Cleared Verification channel configuration")
        await self.refresh(interaction)

    @ui.button(label="Clear Landing Channel", style=discord.ButtonStyle.secondary, row=0)
    async def clear_landing_channel(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["verification_landing_channel_id"] = None
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, "Cleared Verification landing channel configuration")
        await self.refresh(interaction)

    @ui.button(label="Clear Log Channel", style=discord.ButtonStyle.secondary, row=0)
    async def clear_log_channel(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["verification_log_channel_id"] = None
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, "Cleared Verification log channel configuration")
        await self.refresh(interaction)

    @ui.button(label="Back", style=discord.ButtonStyle.danger, row=4)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = VerificationConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(embed=embed, view=dashboard)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        from configuration_module import refresh_interaction
        await refresh_interaction(interaction, embed, view=self)

def setup_verification_commands(tree: app_commands.CommandTree):
    # Verification module relies entirely on UI/Buttons, no root commands needed
    pass
