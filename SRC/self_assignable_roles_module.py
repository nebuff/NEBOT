import discord
from discord import ui
import datetime
from configuration_module import get_guild_config, save_config, safe_join_items, refresh_interaction

class SelfRoleButton(discord.ui.Button):
    def __init__(self, role_id: int, label: str, custom_id: str, style=discord.ButtonStyle.primary, disabled=False):
        super().__init__(label=label, style=style, custom_id=custom_id, disabled=disabled)
        self.role_id = role_id
        
    async def callback(self, interaction: discord.Interaction):
        parts = self.custom_id.split(":")
        guild_id = int(parts[1])
        group_name = parts[2]
        role_id = int(parts[3])
        await handle_self_role_toggle(interaction, guild_id, group_name, role_id)

async def handle_self_role_toggle(interaction: discord.Interaction, guild_id: int, group_name: str, role_id: int):
    cfg = get_guild_config(guild_id)
    if not cfg.get("self_roles_enabled", False):
        await interaction.response.send_message("Self-assignable roles are currently disabled on this server.", ephemeral=True)
        return
        
    groups = cfg.get("self_roles_groups", [])
    group = next((g for g in groups if g["name"] == group_name), None)
    if not group:
        await interaction.response.send_message("This role group configuration was not found.", ephemeral=True)
        return
        
    role_info = next((r for r in group.get("roles", []) if r["role_id"] == role_id), None)
    if not role_info:
        await interaction.response.send_message("This role configuration was not found.", ephemeral=True)
        return
        
    member = interaction.user
    if not isinstance(member, discord.Member):
        await interaction.response.send_message("This action can only be performed in a server.", ephemeral=True)
        return
        
    guild = interaction.guild
    role = guild.get_role(role_id)
    if not role:
        await interaction.response.send_message("The configured Discord role was not found in this server.", ephemeral=True)
        return
        
    # Check group requirements: require_roles
    req_roles = group.get("require_roles", [])
    if req_roles and not any(member.get_role(r_id) is not None for r_id in req_roles):
        req_names = [guild.get_role(r_id).name for r_id in req_roles if guild.get_role(r_id)]
        await interaction.response.send_message(f"You must have at least one of the following roles to use this group: {', '.join(req_names)}", ephemeral=True)
        return
        
    # Check group requirements: ignore_roles
    ign_roles = group.get("ignore_roles", [])
    if ign_roles and any(member.get_role(r_id) is not None for r_id in ign_roles):
        await interaction.response.send_message("You have a role that prevents you from using this group.", ephemeral=True)
        return
        
    # Check role requirements: require_roles
    r_req_roles = role_info.get("require_roles", [])
    if r_req_roles and not any(member.get_role(r_id) is not None for r_id in r_req_roles):
        req_names = [guild.get_role(r_id).name for r_id in r_req_roles if guild.get_role(r_id)]
        await interaction.response.send_message(f"You must have at least one of the following roles to assign this role: {', '.join(req_names)}", ephemeral=True)
        return
        
    # Check role requirements: ignore_roles
    r_ign_roles = role_info.get("ignore_roles", [])
    if r_ign_roles and any(member.get_role(r_id) is not None for r_id in r_ign_roles):
        await interaction.response.send_message("You have a role that prevents you from assigning this role.", ephemeral=True)
        return
        
    has_role = member.get_role(role_id) is not None
    mode = group.get("mode", "none")
    roles_to_remove = []
    
    if has_role:
        if not role_info.get("allow_take_off", True):
            await interaction.response.send_message("This role cannot be removed once assigned.", ephemeral=True)
            return
            
        if mode == "single" and group.get("require_one", False):
            group_role_ids = [r["role_id"] for r in group["roles"]]
            member_group_roles = [r_id for r_id in group_role_ids if member.get_role(r_id)]
            if len(member_group_roles) <= 1:
                await interaction.response.send_message("You must keep at least one role from this group.", ephemeral=True)
                return
                
        if mode == "multi":
            min_amt = group.get("min_amount", 0)
            if min_amt > 0:
                group_role_ids = [r["role_id"] for r in group["roles"]]
                member_group_roles = [r_id for r_id in group_role_ids if member.get_role(r_id)]
                if len(member_group_roles) <= min_amt:
                    await interaction.response.send_message(f"You must keep at least {min_amt} roles from this group.", ephemeral=True)
                    return
                    
        try:
            await member.remove_roles(role, reason="Self-assigned roles menu removal")
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permissions to manage roles. Please verify my hierarchy position.", ephemeral=True)
            return
    else:
        if mode == "multi":
            max_amt = group.get("max_amount", 0)
            if max_amt > 0:
                group_role_ids = [r["role_id"] for r in group["roles"]]
                member_group_roles = [r_id for r_id in group_role_ids if member.get_role(r_id)]
                if len(member_group_roles) >= max_amt:
                    role_to_remove_id = member_group_roles[0]
                    r_to_rem = guild.get_role(role_to_remove_id)
                    if r_to_rem:
                        roles_to_remove.append(r_to_rem)
                        
        elif mode == "single":
            group_role_ids = [r["role_id"] for r in group["roles"]]
            if group.get("auto_take_away", True):
                for r_id in group_role_ids:
                    if r_id != role_id and member.get_role(r_id):
                        r_to_rem = guild.get_role(r_id)
                        if r_to_rem:
                            roles_to_remove.append(r_to_rem)
                            
        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="Self-assigned roles menu replacement")
            await member.add_roles(role, reason="Self-assigned roles menu assignment")
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permissions to manage roles. Please verify my hierarchy position.", ephemeral=True)
            return

    action_text = f"Granted role: **{role.name}**" if not has_role else f"Removed role: **{role.name}**"
    if roles_to_remove:
        action_text += f" (and removed {', '.join(r.name for r in roles_to_remove)})"
        
    await interaction.response.send_message(action_text, ephemeral=True)

class SelfRolesMenuView(discord.ui.View):
    def __init__(self, guild_id: int, group_name: str, member: discord.Member = None):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.group_name = group_name
        
        cfg = get_guild_config(guild_id)
        groups = cfg.get("self_roles_groups", [])
        group = next((g for g in groups if g["name"] == group_name), None)
        
        if group:
            roles_list = group.get("roles", [])
            group_role_ids = [r["role_id"] for r in roles_list]
            
            member_roles = []
            if member:
                member_roles = [r_id for r_id in group_role_ids if member.get_role(r_id)]
                
            mode = group.get("mode", "none")
            min_amt = group.get("min_amount", 0)
            require_one = group.get("require_one", False)
            
            for role_info in roles_list:
                role_id = role_info["role_id"]
                label = role_info.get("name") or f"Role {role_id}"
                custom_id = f"self_role:{guild_id}:{group_name}:{role_id}"
                
                has_role = False
                if member:
                    has_role = member.get_role(role_id) is not None
                    
                disabled = False
                color_style = role_info.get("style") or "blurple"
                style_map = {
                    "blurple": discord.ButtonStyle.primary,
                    "grey": discord.ButtonStyle.secondary,
                    "green": discord.ButtonStyle.success,
                    "red": discord.ButtonStyle.danger
                }
                btn_style = style_map.get(color_style.lower(), discord.ButtonStyle.primary)
                
                if member:
                    if has_role:
                        btn_style = discord.ButtonStyle.success
                        
                        if not role_info.get("allow_take_off", True):
                            disabled = True
                            btn_style = discord.ButtonStyle.secondary
                        elif mode == "single" and require_one and len(member_roles) <= 1:
                            disabled = True
                            btn_style = discord.ButtonStyle.secondary
                        elif mode == "multi" and min_amt > 0 and len(member_roles) <= min_amt:
                            disabled = True
                            btn_style = discord.ButtonStyle.secondary
                            
                self.add_item(SelfRoleButton(role_id, label, custom_id, btn_style, disabled))

class GroupSelectDropdown(discord.ui.Select):
    def __init__(self, guild_id: int, groups: list[dict]):
        options = [
            discord.SelectOption(label=g["name"], description=f"Mode: {g.get('mode', 'none')}")
            for g in groups
        ]
        super().__init__(placeholder="Select a Group to Configure...", options=options, min_values=1, max_values=1, row=1)
        self.guild_id = guild_id
        
    async def callback(self, interaction: discord.Interaction):
        selected_name = self.values[0]
        view = SelfRolesGroupConfigDashboard(self.guild_id, selected_name)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

class CreateGroupModal(discord.ui.Modal, title="Create Self Role Group"):
    group_name = discord.ui.TextInput(label="Group Name", placeholder="e.g. Pronouns", min_length=2, max_length=50)
    group_mode = discord.ui.TextInput(label="Mode (single / multi / none)", placeholder="none", default="none", min_length=4, max_length=6)
    
    def __init__(self, guild_id: int, parent_view):
        super().__init__()
        self.guild_id = guild_id
        self.parent_view = parent_view
        
    async def on_submit(self, interaction: discord.Interaction):
        name = self.group_name.value.strip()
        mode = self.group_mode.value.strip().lower()
        if mode not in ["single", "multi", "none"]:
            await interaction.response.send_message("Invalid mode! Must be one of: `single`, `multi`, or `none`.", ephemeral=True)
            return
            
        cfg = get_guild_config(self.guild_id)
        groups = cfg.get("self_roles_groups", [])
        
        if any(g["name"].lower() == name.lower() for g in groups):
            await interaction.response.send_message("A group with that name already exists!", ephemeral=True)
            return
            
        new_group = {
          "name": name,
          "mode": mode,
          "auto_take_away": True,
          "require_one": False,
          "min_amount": 0,
          "max_amount": 0,
          "require_roles": [],
          "ignore_roles": [],
          "roles": []
        }
        groups.append(new_group)
        cfg["self_roles_groups"] = groups
        save_config()
        
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Created self role group: {name} (mode: {mode})")
        
        await self.parent_view.refresh(interaction)

class SelfRolesConfigDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        
        cfg = get_guild_config(guild_id)
        groups = cfg.get("self_roles_groups", [])
        if groups:
            self.add_item(GroupSelectDropdown(guild_id, groups))
            
    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        enabled = cfg.get("self_roles_enabled", False)
        groups = cfg.get("self_roles_groups", [])
        
        embed = discord.Embed(
            title="Nebot Module: Self-Assignable Roles",
            description=(
                "Manage role menus that allow members to assign roles to themselves via embeds with buttons.\n\n"
                "**Quick Start:**\n"
                "1. Click **Create New Group** and set a name and mode.\n"
                "2. Click the group in the dropdown to add Discord roles and configure restrictions.\n"
                "3. Deploy the role menu embed to a text channel."
            ),
            color=discord.Color.blue()
        )
        embed.add_field(name="Module Status", value="[ENABLED]" if enabled else "[DISABLED]", inline=True)
        embed.add_field(name="Total Groups", value=f"{len(groups)} group(s)", inline=True)
        
        if groups:
            grp_list = "\n".join(f"• **{g['name']}** ({g.get('mode', 'none')} mode, {len(g.get('roles', []))} roles)" for g in groups)
            embed.add_field(name="Groups Overview", value=grp_list, inline=False)
            
        return embed

    @ui.button(label="Toggle Module", style=discord.ButtonStyle.primary, row=0)
    async def toggle_module(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["self_roles_enabled"] = not cfg.get("self_roles_enabled", False)
        save_config()
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Toggled Self-Assignable Roles module to `{'enabled' if cfg['self_roles_enabled'] else 'disabled'}`")
        await self.refresh(interaction)

    @ui.button(label="Create New Group", style=discord.ButtonStyle.success, row=0)
    async def create_group_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(CreateGroupModal(self.guild_id, self))

    @ui.button(label="Back to Modules", style=discord.ButtonStyle.danger, row=2)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        from admin_ui_module import ModuleSelectView
        view = ModuleSelectView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    async def refresh(self, interaction: discord.Interaction):
        new_view = SelfRolesConfigDashboard(self.guild_id)
        embed = new_view.build_embed()
        await refresh_interaction(interaction, embed, view=new_view)

class RoleRemoveSelect(discord.ui.Select):
    def __init__(self, guild_id: int, group_name: str, roles: list[dict]):
        options = []
        for r in roles:
            options.append(discord.SelectOption(label=r.get("name") or f"Role {r['role_id']}", value=str(r["role_id"])))
        super().__init__(placeholder="Select a Role to Remove...", options=options, min_values=1, max_values=1, row=2)
        self.guild_id = guild_id
        self.group_name = group_name
        
    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        cfg = get_guild_config(self.guild_id)
        groups = cfg.get("self_roles_groups", [])
        group = next((g for g in groups if g["name"] == self.group_name), None)
        if group:
            roles = group.get("roles", [])
            group["roles"] = [r for r in roles if r["role_id"] != role_id]
            save_config()
            
            from configuration_module import log_setting_change_task
            log_setting_change_task(interaction.guild, interaction.user, f"Removed role {role_id} from group: {self.group_name}")
            
            if self.view:
                await self.view.refresh(interaction)

class AddRoleSelect(discord.ui.RoleSelect):
    def __init__(self, guild_id: int, group_name: str):
        super().__init__(placeholder="Select a Role to Add...", min_values=1, max_values=1, row=1)
        self.guild_id = guild_id
        self.group_name = group_name
        
    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        cfg = get_guild_config(self.guild_id)
        groups = cfg.get("self_roles_groups", [])
        group = next((g for g in groups if g["name"] == self.group_name), None)
        if group:
            roles = group.get("roles", [])
            if any(r["role_id"] == role.id for r in roles):
                await interaction.response.send_message("This role is already in the group!", ephemeral=True)
                return
            new_role = {
                "role_id": role.id,
                "name": role.name,
                "allow_take_off": True,
                "require_roles": [],
                "ignore_roles": [],
                "style": "blurple"
            }
            roles.append(new_role)
            group["roles"] = roles
            save_config()
            
            from configuration_module import log_setting_change_task
            log_setting_change_task(interaction.guild, interaction.user, f"Added role {role.name} to group: {self.group_name}")
            
            if self.view:
                await self.view.refresh(interaction)

class DeployMenuSelect(discord.ui.ChannelSelect):
    def __init__(self, guild_id: int, group_name: str):
        super().__init__(placeholder="Deploy Role Menu to Channel...", channel_types=[discord.ChannelType.text], min_values=1, max_values=1, row=3)
        self.guild_id = guild_id
        self.group_name = group_name
        
    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        real_channel = interaction.guild.get_channel(channel.id)
        if not real_channel:
            try:
                real_channel = await interaction.guild.fetch_channel(channel.id)
            except Exception:
                pass
        if not real_channel:
            await interaction.response.send_message("Failed to resolve the selected channel.", ephemeral=True)
            return

        cfg = get_guild_config(self.guild_id)
        groups = cfg.get("self_roles_groups", [])
        group = next((g for g in groups if g["name"] == self.group_name), None)
        if not group:
            await interaction.response.send_message("Group not found!", ephemeral=True)
            return
            
        roles_list = group.get("roles", [])
        if not roles_list:
            await interaction.response.send_message("Cannot deploy an empty role group!", ephemeral=True)
            return
            
        title = group.get("display_name") or f"Self-Assignable Roles: {group['name']}"
        desc = group.get("description") or "Select the roles you want to assign/remove by clicking the buttons below."
        color_str = group.get("color") or "blue"
        
        color_map = {
            "blue": discord.Color.blue(),
            "red": discord.Color.red(),
            "green": discord.Color.green(),
            "teal": discord.Color.teal(),
            "orange": discord.Color.orange(),
            "purple": discord.Color.purple(),
            "gold": discord.Color.gold(),
            "grey": discord.Color.light_grey()
        }
        embed_color = color_map.get(color_str.lower(), discord.Color.blue())
        
        embed = discord.Embed(
            title=title,
            description=desc,
            color=embed_color
        )
        mode_desc = "Select one role" if group.get("mode") == "single" else "Select multiple roles"
        embed.add_field(name="Mode", value=mode_desc, inline=False)
        
        view = SelfRolesMenuView(self.guild_id, self.group_name)
        try:
            await real_channel.send(embed=embed, view=view)
            interaction.client.add_view(view)
            await interaction.response.send_message(f"Role Menu deployed successfully to {real_channel.mention}!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f"I don't have permissions to send messages to {real_channel.mention}.", ephemeral=True)

class EditLimitsModal(discord.ui.Modal, title="Edit Group Multi Limits"):
    min_amt = discord.ui.TextInput(label="Minimum Amount", placeholder="0", default="0", min_length=1, max_length=2)
    max_amt = discord.ui.TextInput(label="Maximum Amount", placeholder="0", default="0", min_length=1, max_length=2)
    
    def __init__(self, guild_id: int, group_name: str, parent_view):
        super().__init__()
        self.guild_id = guild_id
        self.group_name = group_name
        self.parent_view = parent_view
        
    async def on_submit(self, interaction: discord.Interaction):
        try:
            min_val = int(self.min_amt.value.strip())
            max_val = int(self.max_amt.value.strip())
        except ValueError:
            await interaction.response.send_message("Invalid integers!", ephemeral=True)
            return
            
        cfg = get_guild_config(self.guild_id)
        groups = cfg.get("self_roles_groups", [])
        group = next((g for g in groups if g["name"] == self.group_name), None)
        if group:
            group["min_amount"] = min_val
            group["max_amount"] = max_val
            save_config()
            
            from configuration_module import log_setting_change_task
            log_setting_change_task(interaction.guild, interaction.user, f"Updated limits on group {self.group_name}: min={min_val}, max={max_val}")
            
            await self.parent_view.refresh(interaction)

class SetTitleModal(discord.ui.Modal, title="Set Embed Title"):
    val = discord.ui.TextInput(label="Embed Title", placeholder="e.g. Select your Pronouns", min_length=2, max_length=100)
    
    def __init__(self, guild_id, group_name, parent_view):
        super().__init__()
        self.guild_id = guild_id
        self.group_name = group_name
        self.parent_view = parent_view
        
    async def on_submit(self, interaction):
        cfg = get_guild_config(self.guild_id)
        group = next((g for g in cfg.get("self_roles_groups", []) if g["name"] == self.group_name), None)
        if group:
            group["display_name"] = self.val.value.strip()
            save_config()
            await self.parent_view.refresh(interaction)

class SetDescriptionModal(discord.ui.Modal, title="Set Embed Description"):
    val = discord.ui.TextInput(label="Embed Description", placeholder="e.g. Choose one or more options...", style=discord.TextStyle.long, min_length=2, max_length=500)
    
    def __init__(self, guild_id, group_name, parent_view):
        super().__init__()
        self.guild_id = guild_id
        self.group_name = group_name
        self.parent_view = parent_view
        
    async def on_submit(self, interaction):
        cfg = get_guild_config(self.guild_id)
        group = next((g for g in cfg.get("self_roles_groups", []) if g["name"] == self.group_name), None)
        if group:
            group["description"] = self.val.value.strip()
            save_config()
            await self.parent_view.refresh(interaction)

class SetColorModal(discord.ui.Modal, title="Set Embed Color"):
    val = discord.ui.TextInput(label="Color (blue/red/green/teal/purple/etc)", placeholder="blue", min_length=3, max_length=10)
    
    def __init__(self, guild_id, group_name, parent_view):
        super().__init__()
        self.guild_id = guild_id
        self.group_name = group_name
        self.parent_view = parent_view
        
    async def on_submit(self, interaction):
        color = self.val.value.strip().lower()
        if color not in ["blue", "red", "green", "teal", "orange", "purple", "gold", "grey"]:
            await interaction.response.send_message("Invalid color name! Must be blue/red/green/teal/orange/purple/gold/grey.", ephemeral=True)
            return
        cfg = get_guild_config(self.guild_id)
        group = next((g for g in cfg.get("self_roles_groups", []) if g["name"] == self.group_name), None)
        if group:
            group["color"] = color
            save_config()
            await self.parent_view.refresh(interaction)

class GroupDetailsSelect(discord.ui.Select):
    def __init__(self, guild_id: int, group_name: str):
        options = [
            discord.SelectOption(label="Set Embed Title", value="title", description="Customize the embed title"),
            discord.SelectOption(label="Set Embed Description", value="desc", description="Customize the embed description"),
            discord.SelectOption(label="Set Embed Color", value="color", description="Customize the embed border color"),
            discord.SelectOption(label="Configure Button Colors", value="btn_colors", description="Change colors of role buttons")
        ]
        super().__init__(placeholder="Configure Group Embed & Colors...", options=options, min_values=1, max_values=1, row=4)
        self.guild_id = guild_id
        self.group_name = group_name
        
    async def callback(self, interaction: discord.Interaction):
        sel = self.values[0]
        if sel == "title":
            await interaction.response.send_modal(SetTitleModal(self.guild_id, self.group_name, self.view))
        elif sel == "desc":
            await interaction.response.send_modal(SetDescriptionModal(self.guild_id, self.group_name, self.view))
        elif sel == "color":
            await interaction.response.send_modal(SetColorModal(self.guild_id, self.group_name, self.view))
        elif sel == "btn_colors":
            view = RoleButtonColorDashboard(self.guild_id, self.group_name)
            embed = view.build_embed()
            await interaction.response.edit_message(embed=embed, view=view)

class RoleColorSelectDropdown(discord.ui.Select):
    def __init__(self, guild_id: int, group_name: str, roles: list[dict]):
        options = [
            discord.SelectOption(label=r.get("name") or f"Role {r['role_id']}", value=str(r["role_id"]), description=f"Style: {r.get('style', 'blurple')}")
            for r in roles
        ]
        super().__init__(placeholder="Select a Role to Style...", options=options, min_values=1, max_values=1, row=1)
        self.guild_id = guild_id
        self.group_name = group_name
        
    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        self.view.selected_role_id = role_id
        await interaction.response.defer()
        
class ButtonColorOptionDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Blurple (Primary)", value="blurple"),
            discord.SelectOption(label="Grey (Secondary)", value="grey"),
            discord.SelectOption(label="Green (Success)", value="green"),
            discord.SelectOption(label="Red (Danger)", value="red")
        ]
        super().__init__(placeholder="Choose Button Color...", options=options, min_values=1, max_values=1, row=2)
        
    async def callback(self, interaction: discord.Interaction):
        role_id = getattr(self.view, "selected_role_id", None)
        if not role_id:
            await interaction.response.send_message("Please select a role first!", ephemeral=True)
            return
            
        color = self.values[0]
        cfg = get_guild_config(self.view.guild_id)
        group = next((g for g in cfg.get("self_roles_groups", []) if g["name"] == self.view.group_name), None)
        if group:
            role_info = next((r for r in group["roles"] if r["role_id"] == role_id), None)
            if role_info:
                role_info["style"] = color
                save_config()
                from configuration_module import log_setting_change_task
                log_setting_change_task(interaction.guild, interaction.user, f"Set style of role {role_id} in group {self.view.group_name} to {color}")
                await self.view.refresh(interaction)

class RoleButtonColorDashboard(ui.View):
    def __init__(self, guild_id: int, group_name: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.group_name = group_name
        self.selected_role_id = None
        
        cfg = get_guild_config(guild_id)
        group = next((g for g in cfg.get("self_roles_groups", []) if g["name"] == group_name), None)
        if group:
            roles = group.get("roles", [])
            if roles:
                self.add_item(RoleColorSelectDropdown(guild_id, group_name, roles))
                self.add_item(ButtonColorOptionDropdown())
                
    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        group = next((g for g in cfg.get("self_roles_groups", []) if g["name"] == self.group_name), None)
        
        embed = discord.Embed(
            title=f"Style Buttons: {self.group_name}",
            description="Select a role and then select a button color style to apply.",
            color=discord.Color.blue()
        )
        
        roles_str = "None configured."
        if group:
            roles = group.get("roles", [])
            if roles:
                roles_str = "\n".join(f"• <@&{r['role_id']}>: **{r.get('style', 'blurple').upper()}**" for r in roles)
        embed.add_field(name="Role Button Styles", value=roles_str, inline=False)
        return embed
        
    @ui.button(label="Back to Group Config", style=discord.ButtonStyle.secondary, row=4)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        view = SelfRolesGroupConfigDashboard(self.guild_id, self.group_name)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
        
    async def refresh(self, interaction: discord.Interaction):
        new_view = RoleButtonColorDashboard(self.guild_id, self.group_name)
        embed = new_view.build_embed()
        await refresh_interaction(interaction, embed, view=new_view)

class SelfRolesGroupConfigDashboard(ui.View):
    def __init__(self, guild_id: int, group_name: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.group_name = group_name
        
        self.add_item(AddRoleSelect(guild_id, group_name))
        
        cfg = get_guild_config(guild_id)
        groups = cfg.get("self_roles_groups", [])
        group = next((g for g in groups if g["name"] == group_name), None)
        if group:
            roles = group.get("roles", [])
            if roles:
                self.add_item(RoleRemoveSelect(guild_id, group_name, roles))
            self.add_item(DeployMenuSelect(guild_id, group_name))
            self.add_item(GroupDetailsSelect(guild_id, group_name))
            
    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        groups = cfg.get("self_roles_groups", [])
        group = next((g for g in groups if g["name"] == self.group_name), None)
        
        if not group:
            return discord.Embed(title="Error", description="Group not found.", color=discord.Color.red())
            
        embed = discord.Embed(
            title=f"Configure Group: {group['name']}",
            description="Manage settings, add/remove roles, and deploy the interactive role selection menu.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Mode", value=group.get("mode", "none").upper(), inline=True)
        
        if group.get("mode") == "single":
            embed.add_field(name="Auto Take Away", value="YES" if group.get("auto_take_away", True) else "NO", inline=True)
            embed.add_field(name="Require One", value="YES" if group.get("require_one", False) else "NO", inline=True)
        elif group.get("mode") == "multi":
            embed.add_field(name="Min Amount", value=str(group.get("min_amount", 0)), inline=True)
            embed.add_field(name="Max Amount", value=str(group.get("max_amount", 0)), inline=True)
            
        # Display custom details
        c_title = group.get("display_name") or "Default"
        c_desc = group.get("description") or "Default"
        c_color = group.get("color") or "blue"
        embed.add_field(name="Embed Custom Title", value=c_title, inline=True)
        embed.add_field(name="Embed Custom Desc", value=c_desc[:50] + ("..." if len(c_desc) > 50 else ""), inline=True)
        embed.add_field(name="Embed Color Border", value=c_color.upper(), inline=True)
        
        roles_str = "None configured."
        roles = group.get("roles", [])
        if roles:
            roles_str = "\n".join(f"• <@&{r['role_id']}> ({r.get('name') or 'Unnamed'}) [Style: {r.get('style', 'blurple').upper()}]" for r in roles)
        embed.add_field(name="Configured Roles", value=roles_str, inline=False)
        return embed

    @ui.button(label="Toggle Mode", style=discord.ButtonStyle.primary, row=0)
    async def toggle_mode(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        groups = cfg.get("self_roles_groups", [])
        group = next((g for g in groups if g["name"] == self.group_name), None)
        if group:
            modes = ["none", "single", "multi"]
            curr = group.get("mode", "none")
            next_idx = (modes.index(curr) + 1) % len(modes)
            group["mode"] = modes[next_idx]
            save_config()
            await self.refresh(interaction)

    @ui.button(label="Edit Limits / Flags", style=discord.ButtonStyle.primary, row=0)
    async def edit_limits(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        groups = cfg.get("self_roles_groups", [])
        group = next((g for g in groups if g["name"] == self.group_name), None)
        if group:
            if group.get("mode") == "single":
                group["auto_take_away"] = not group.get("auto_take_away", True)
                group["require_one"] = not group.get("require_one", False)
                save_config()
                await self.refresh(interaction)
            elif group.get("mode") == "multi":
                await interaction.response.send_modal(EditLimitsModal(self.guild_id, self.group_name, self))
            else:
                await interaction.response.send_message("Limits are only configurable in `single` or `multi` mode.", ephemeral=True)

    @ui.button(label="Delete Group", style=discord.ButtonStyle.danger, row=0)
    async def delete_group(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        groups = cfg.get("self_roles_groups", [])
        cfg["self_roles_groups"] = [g for g in groups if g["name"] != self.group_name]
        save_config()
        
        from configuration_module import log_setting_change_task
        log_setting_change_task(interaction.guild, interaction.user, f"Deleted self role group: {self.group_name}")
        
        view = SelfRolesConfigDashboard(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Back to Dashboard", style=discord.ButtonStyle.secondary, row=0)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        view = SelfRolesConfigDashboard(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    async def refresh(self, interaction: discord.Interaction):
        new_view = SelfRolesGroupConfigDashboard(self.guild_id, self.group_name)
        embed = new_view.build_embed()
        await refresh_interaction(interaction, embed, view=new_view)
