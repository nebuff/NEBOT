import re
import uuid
import datetime
import discord
from discord import ui
import configuration_module  # Imported at module level
from configuration_module import get_guild_config, save_config, is_admin, safe_join_items

# Leetspeak translation map
LEET_MAP = {
    '1': 'i', '!': 'i', '|': 'i',
    '0': 'o',
    '@': 'a', '4': 'a',
    '3': 'e',
    '$': 's', '5': 's',
    '7': 't',
    '8': 'b',
    '9': 'g',
}

LEET_TRANSLATE_TABLE = str.maketrans(LEET_MAP)

_regex_cache = {}

def get_compiled_regex(pattern: str):
    """Compile and cache regex patterns to avoid rebuild latency."""
    if pattern not in _regex_cache:
        try:
            _regex_cache[pattern] = re.compile(pattern, re.IGNORECASE)
        except Exception:
            _regex_cache[pattern] = None
    return _regex_cache[pattern]

_emoji_trans_map = {
    chr(o): chr(97 + (o - 127462)) for o in range(127462, 127488) # Map regional indicators (-) to ascii letters (a-z)
}
# Map common letter block emojis using escape sequences to prevent literal emojis in codebase
_emoji_trans_map.update({
    "\U0001f170": "a", "\U0001f171": "b", "\U0001f17e": "o", "\U0001f17f": "p", "\u24c2": "m",
    "\U0001f18e": "ab", "\U0001f191": "cl", "\U0001f192": "cool", "\U0001f193": "free", "\U0001f194": "id",
    "\U0001f195": "new", "\U0001f196": "ng", "\U0001f197": "ok", "\U0001f198": "sos", "\U0001f199": "up", "\U0001f19a": "vs"
})
EMOJI_TRANSLATE_TABLE = str.maketrans(_emoji_trans_map)

def convert_emojis_to_text(text: str) -> str:
    return text.translate(EMOJI_TRANSLATE_TABLE)

HOMOGLYPH_MAP = {
    # Cyrillic lowercase
    '\u0430': 'a', # а
    '\u0435': 'e', # е
    '\u043e': 'o', # о
    '\u0440': 'p', # р
    '\u0441': 'c', # с
    '\u0445': 'x', # х
    '\u0443': 'y', # у
    '\u0456': 'i', # і
    '\u0458': 'j', # ј
    '\u0455': 's', # ѕ
    # Cyrillic uppercase
    '\u0410': 'a', # А
    '\u0415': 'e', # Е
    '\u041e': 'o', # О
    '\u0420': 'p', # Р
    '\u0421': 'c', # С
    '\u0425': 'x', # Х
    '\u0423': 'y', # У
    '\u0406': 'i', # І
    '\u0408': 'j', # Ј
    '\u0405': 's', # Ѕ
    # Greek lowercase
    '\u03b1': 'a', # α
    '\u03b5': 'e', # ε
    '\u03bf': 'o', # ο
    '\u03ba': 'k', # κ
    '\u03bd': 'v', # ν
    '\u03c4': 't', # τ
    '\u03c7': 'x', # χ
    '\u03c5': 'y', # υ
    '\u03c1': 'p', # ρ
    # Greek uppercase
    '\u0391': 'a', # Α
    '\u0395': 'e', # Ε
    '\u039f': 'o', # Ο
    '\u039a': 'k', # Κ
    '\u039d': 'v', # Ν
    '\u03a4': 't', # Τ
    '\u03a7': 'x', # Χ
    '\u03a5': 'y', # Υ
    '\u03a1': 'p', # Ρ
}

HOMOGLYPH_TRANSLATE_TABLE = str.maketrans(HOMOGLYPH_MAP)

def convert_homoglyphs_to_text(text: str) -> str:
    return text.translate(HOMOGLYPH_TRANSLATE_TABLE)

def _has_any_role(member: discord.Member, role_ids: list[int]) -> bool:
    """Optimized O(1) role lookup bypassing list generation."""
    if hasattr(member, 'get_role'):
        return any(member.get_role(rid) is not None for rid in role_ids)

    return any(getattr(role, 'id', None) in role_ids for role in getattr(member, 'roles', []))

def normalize_text(text: str) -> tuple[str, str, str]:
    """
    Sanitize text to lowercase, translate leetspeak, and return:
    - spaced: text with non-alphanumeric chars replaced by space (collapsed).
    - merged: same as spaced but with single letters merged.
    - condensed: same as spaced but with all whitespace removed.
    """
    text_lower = text.lower()
    
    # Apply leetspeak translations
    leet_str = text_lower.translate(LEET_TRANSLATE_TABLE)
    
    # Replace non-alphanumeric with spaces, keeping original multiple spaces
    spaced_raw = re.sub(r'[^a-z0-9]', ' ', leet_str)
    
    # Merged spaced letters logic using spaced_raw to preserve double-space boundaries
    parts = spaced_raw.split(' ')
    result = []
    buffer = []
    for p in parts:
        if p == '':
            if buffer:
                result.append("".join(buffer))
                buffer = []
        elif len(p) == 1:
            buffer.append(p)
        else:
            if buffer:
                result.append("".join(buffer))
                buffer = []
            result.append(p)
    if buffer:
        result.append("".join(buffer))
    merged = " ".join(r for r in result if r)
    
    # Spaced string (collapse spacing)
    spaced = " ".join(spaced_raw.split())
    
    # Condensed string (all whitespace removed)
    condensed = re.sub(r'\s+', '', spaced_raw)
    
    return spaced, merged, condensed

async def log_fallback_automod_violation(guild, member, filter_name, severity, details, channel=None):
    """Graceful degradation warning logger when Warning Tracker is disabled or errored."""
    cfg = get_guild_config(guild.id)
    log_ch_id = cfg.get("global_log_channel_id")
    if log_ch_id:
        log_ch = guild.get_channel(log_ch_id)
        if not log_ch:
            try:
                log_ch = await guild.fetch_channel(log_ch_id)
            except Exception:
                pass
        if log_ch:
            embed = discord.Embed(
                title="AutoMod Violation (AutoMod)",
                description=f"User {member.mention} triggered AutoMod filter `{filter_name}`.\nWarning Tracker is disabled or unavailable.",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="Severity", value=str(severity or "Low"), inline=True)
            embed.add_field(name="Offending Message Preview", value=str(details[:1024] or "No preview available"), inline=False)
            try:
                await log_ch.send(embed=embed)
            except Exception:
                pass
                
    if channel:
        try:
            await channel.send(
                f"{member.mention} Warning: Your message was deleted for violating the Mod filter `{filter_name}`.",
                delete_after=10
            )
        except Exception:
            pass

REVERSE_LEET = {
    'a': '[a@4]',
    'i': '[i1!|]',
    'o': '[o0]',
    'e': '[e3]',
    's': '[s$5]',
    't': '[t7]',
    'b': '[b8]',
    'g': '[g9]',
}

def make_bypass_regex(keyword: str, is_wildcard_start: bool = False, is_wildcard_end: bool = False) -> str:
    pattern_parts = []
    for char in keyword:
        if char.isalnum():
            char_class = REVERSE_LEET.get(char.lower(), re.escape(char))
            pattern_parts.append(rf"{char_class}+")
        else:
            pattern_parts.append(r"[^a-zA-Z0-9]*")
            
    raw_pattern = r"[^a-zA-Z0-9]*".join(pattern_parts)
    import re as regex_lib
    pattern = regex_lib.sub(r'(\[\^a-zA-Z0-9\]\*)+', r'[^a-zA-Z0-9]*', raw_pattern)
    
    start_anchor = "" if is_wildcard_start else r"\b"
    end_anchor = "" if is_wildcard_end else r"\b"
    return rf"{start_anchor}{pattern}{end_anchor}"

def parse_keyword(kw: str) -> tuple[bool, bool, str, bool, bool]:
    """
    Parses a keyword string into (is_allowed, is_regex, pattern_str, is_wildcard_start, is_wildcard_end).
    Example:
      "r:fuck.*" -> (False, True, "fuck.*", False, False)
      "a:r:class.*" -> (True, True, "class.*", False, False)
      "a:*grape*" -> (True, False, "grape", True, True)
      "**cunt**" -> (False, False, "cunt", False, False)
      "cunt" -> (False, False, "cunt", False, False)
      "*cunt" -> (False, False, "cunt", True, False)
      "cunt*" -> (False, False, "cunt", False, True)
    """
    kw_clean = kw.lower().strip()
    is_allowed = False
    
    if kw_clean.startswith("a:"):
        is_allowed = True
        kw_clean = kw_clean[2:].strip()
        
    is_regex = False
    if kw_clean.startswith("r:"):
        is_regex = True
        pattern_str = kw_clean[2:].strip()
        is_wildcard_start = False
        is_wildcard_end = False
    else:
        # Translate leetspeak in plain keyword to match normalized string format
        kw_clean = kw_clean.translate(LEET_TRANSLATE_TABLE)
        
        is_wildcard_start = False
        is_wildcard_end = False
        if kw_clean.startswith("**") and kw_clean.endswith("**") and len(kw_clean) >= 4:
            pattern_str = kw_clean[2:-2].strip()
        else:
            # Single/ends wildcard check
            if kw_clean.startswith("\\*"):
                is_wildcard_start = True
                kw_clean = kw_clean[2:].strip()
            elif kw_clean.startswith("*"):
                is_wildcard_start = True
                kw_clean = kw_clean[1:].strip()

            if kw_clean.endswith("\\*"):
                is_wildcard_end = True
                kw_clean = kw_clean[:-2].strip()
            elif kw_clean.endswith("*"):
                is_wildcard_end = True
                kw_clean = kw_clean[:-1].strip()
            
            pattern_str = kw_clean
            
    return is_allowed, is_regex, pattern_str, is_wildcard_start, is_wildcard_end

def get_spans_in_text(text: str, patterns: list[tuple[bool, str, bool, bool]], use_word_boundary: bool = True) -> list[tuple[int, int]]:
    """
    Get all match spans for a list of parsed patterns (is_regex, pattern_str, is_wildcard_start, is_wildcard_end) in text.
    """
    spans = []
    for is_regex, pattern_str, is_wildcard_start, is_wildcard_end in patterns:
        if is_regex:
            rx = get_compiled_regex(pattern_str)
            if rx:
                for m in rx.finditer(text):
                    spans.append(m.span())
        else:
            if use_word_boundary:
                pat = make_bypass_regex(pattern_str, is_wildcard_start, is_wildcard_end)
                rx = get_compiled_regex(pat)
            else:
                pat = make_bypass_regex(pattern_str, is_wildcard_start=True, is_wildcard_end=True)
                rx = get_compiled_regex(pat)
            if rx:
                for m in rx.finditer(text):
                    spans.append(m.span())
    return spans

def has_unallowed_match(text: str, banned: list[tuple[bool, str, bool]], allowed: list[tuple[bool, str, bool]], use_word_boundary: bool = True) -> bool:
    """
    Checks if there is a banned match span in text that is not enclosed by any allowed match span.
    """
    banned_spans = get_spans_in_text(text, banned, use_word_boundary)
    if not banned_spans:
        return False
    allowed_spans = get_spans_in_text(text, allowed, use_word_boundary)
    for b_start, b_end in banned_spans:
        enclosed = False
        for a_start, a_end in allowed_spans:
            if a_start <= b_start and b_end <= a_end:
                enclosed = True
                break
        if not enclosed:
            return True
    return False

def merge_spans(spans):
    """
    Merge overlapping or adjacent spans.
    """
    if not spans:
        return []
    sorted_spans = sorted(spans, key=lambda x: (x[0], -x[1]))
    merged = [sorted_spans[0]]
    for current in sorted_spans[1:]:
        prev_start, prev_end = merged[-1]
        curr_start, curr_end = current
        if curr_start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, curr_end))
        else:
            merged.append(current)
    return merged

def bold_offending_words(raw_content: str, filter_profile: dict) -> str:
    keywords = filter_profile.get("keywords", [])
    filter_emojis = filter_profile.get("filter_emojis", False)
    filter_homoglyphs = filter_profile.get("filter_homoglyphs", False)
    
    if filter_emojis:
        raw_content = convert_emojis_to_text(raw_content)
    if filter_homoglyphs:
        raw_content = convert_homoglyphs_to_text(raw_content)
        
    banned_pats = []
    allowed_pats = []
    for kw in keywords:
        is_allowed, is_regex, pattern_str, is_wildcard_start, is_wildcard_end = parse_keyword(kw)
        if not pattern_str:
            continue
        if is_regex:
            pat = pattern_str
        else:
            pat = make_bypass_regex(pattern_str, is_wildcard_start, is_wildcard_end)
            
        if is_allowed:
            allowed_pats.append(pat)
        else:
            banned_pats.append(pat)
            
    banned_spans = []
    for pat in banned_pats:
        rx = get_compiled_regex(pat)
        if rx:
            for m in rx.finditer(raw_content):
                banned_spans.append(m.span())
                
    allowed_spans = []
    for pat in allowed_pats:
        rx = get_compiled_regex(pat)
        if rx:
            for m in rx.finditer(raw_content):
                allowed_spans.append(m.span())
                
    filtered_spans = []
    for b_start, b_end in banned_spans:
        enclosed = False
        for a_start, a_end in allowed_spans:
            if a_start <= b_start and b_end <= a_end:
                enclosed = True
                break
        if not enclosed:
            filtered_spans.append((b_start, b_end))
            
    merged = merge_spans(filtered_spans)
    
    bolded_content = raw_content
    for start, end in reversed(merged):
        bolded_content = bolded_content[:start] + f"**{bolded_content[start:end]}**" + bolded_content[end:]
        
    return bolded_content

def prepare_message_for_word_check(text: str) -> str:
    out = []
    import unicodedata
    for w in text.split():
        w1_chars = []
        w2_chars = []
        for c in w:
            cat = unicodedata.category(c)
            if cat.startswith('P') or cat.startswith('S'):
                w1_chars.append(' ')
            else:
                w1_chars.append(c)
                w2_chars.append(c)
        w1 = "".join(w1_chars)
        w2 = "".join(w2_chars)
        
        word_variants = [w1]
        if w1 != w2 and w1 != w:
            word_variants.extend([w2, w])
        elif w1 != w2:
            word_variants.append(w2)
        elif w1 != w:
            word_variants.append(w)
        out.append(" ".join(word_variants))
    return " ".join(out)

KNOWN_CONDITIONS = (
    "c:age:", "c:member_age:", "c:bot", "c:human", 
    "c:attachment", "c:no_attachment", "c:edit", "c:new",
    "c:thread", "c:no_thread", "c:forward"
)

KNOWN_TRIGGERS = (
    "t:mentions:", "t:caps:", "t:length:", "t:spam:",
    "t:invite", "t:link", "t:phishing"
)

def parse_keyword_tags(keywords: list[str]) -> tuple[list[str], list[str], list[str]]:
    conditions = []
    triggers = []
    regular = []
    for kw in keywords:
        kw_clean = kw.strip().lower()
        is_tag = False
        for cond in KNOWN_CONDITIONS:
            if kw_clean == cond or kw_clean.startswith(cond):
                conditions.append(kw_clean)
                is_tag = True
                break
        if not is_tag:
            for trig in KNOWN_TRIGGERS:
                if kw_clean == trig or kw_clean.startswith(trig):
                    triggers.append(kw_clean)
                    is_tag = True
                    break
        if not is_tag:
            regular.append(kw)
    return conditions, triggers, regular

def evaluate_condition(cond: str, member: discord.Member, message: discord.Message = None) -> bool:
    utcnow = datetime.datetime.now(datetime.timezone.utc)
    
    if cond.startswith("c:age:"):
        try:
            minutes = int(cond.split(":")[2])
        except (IndexError, ValueError):
            return True
        created_at = member.created_at
        delta = utcnow - created_at
        return (delta.total_seconds() / 60) <= minutes
        
    elif cond.startswith("c:member_age:"):
        try:
            minutes = int(cond.split(":")[2])
        except (IndexError, ValueError):
            return True
        joined_at = member.joined_at
        if not joined_at:
            return True
        delta = utcnow - joined_at
        return (delta.total_seconds() / 60) <= minutes
        
    elif cond == "c:bot":
        return member.bot
        
    elif cond == "c:human":
        return not member.bot
        
    elif cond == "c:attachment":
        if not message:
            return False
        return len(message.attachments) > 0
        
    elif cond == "c:no_attachment":
        if not message:
            return True
        return len(message.attachments) == 0
        
    elif cond == "c:edit":
        if not message:
            return False
        return message.edited_at is not None
        
    elif cond == "c:new":
        if not message:
            return True
        return message.edited_at is None
        
    elif cond == "c:thread":
        if not message:
            return False
        return isinstance(message.channel, discord.Thread)
        
    elif cond == "c:no_thread":
        if not message:
            return True
        return not isinstance(message.channel, discord.Thread)
        
    elif cond == "c:forward":
        if not message:
            return False
        ref = message.reference
        if ref and hasattr(ref, "type"):
            return str(ref.type) == "MessageReferenceType.forward" or getattr(ref.type, "value", None) == 1
        return False
        
    return True

async def evaluate_trigger(trigger: str, member: discord.Member, message: discord.Message = None) -> bool:
    if trigger.startswith("t:spam:"):
        try:
            parts = trigger.split(":")
            threshold = int(parts[2])
            seconds = int(parts[3])
        except (IndexError, ValueError):
            return False
            
        if not message:
            return False
            
        time_limit = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=seconds)
        author_id = message.author.id
        content_normalized = message.content.strip().lower()
        attachment_count = len(message.attachments)
        
        count = 1
        try:
            async for old_msg in message.channel.history(limit=50, before=message):
                if old_msg.created_at < time_limit:
                    break
                if old_msg.author.id != author_id:
                    continue
                if len(old_msg.attachments) != attachment_count:
                    break
                if old_msg.content.strip().lower() == content_normalized:
                    count += 1
                else:
                    break
        except Exception:
            pass
            
        return count >= threshold
        
    elif trigger.startswith("t:mentions:"):
        try:
            threshold = int(trigger.split(":")[2])
        except (IndexError, ValueError):
            return False
        if not message:
            return False
        unique_mentions = len(set(m.id for m in message.mentions))
        return unique_mentions >= threshold
        
    elif trigger.startswith("t:caps:"):
        try:
            parts = trigger.split(":")
            percentage = int(parts[2])
            min_length = int(parts[3]) if len(parts) > 3 else 5
        except (IndexError, ValueError):
            return False
        if not message or not message.content:
            return False
        content = message.content
        if len(content) < min_length:
            return False
        total_capitalisable = 0
        num_caps = 0
        for c in content:
            if c.isupper():
                num_caps += 1
                total_capitalisable += 1
            elif c.upper() != c.lower():
                total_capitalisable += 1
        if total_capitalisable == 0:
            return False
        actual_pct = (num_caps * 100) // total_capitalisable
        return actual_pct >= percentage
        
    elif trigger.startswith("t:length:"):
        try:
            threshold = int(trigger.split(":")[2])
        except (IndexError, ValueError):
            return False
        if not message or not message.content:
            return False
        return len(message.content) >= threshold
        
    elif trigger == "t:invite":
        if not message or not message.content:
            return False
        import re
        invite_patterns = [
            r"(?i)(discord\.gg|discordapp\.com[\/\\]+invite|discord\.com[\/\\]+invite)(?:\/+#)?[\/\\]+([a-zA-Z0-9-]+)",
            r"(?i)discord\.me\/+.+",
            r"(?i)invite\.gg\/+.+",
            r"(?i)discord\.io\/+.+",
            r"(?i)discord\.li\/+.+",
            r"(?i)disboard\.org\/+server\/+join\/+.+",
            r"(?i)discordy\.com\/+server\+.php"
        ]
        for pat in invite_patterns:
            if re.search(pat, message.content):
                return True
        return False
        
    elif trigger == "t:link":
        if not message or not message.content:
            return False
        import re
        link_pat = r"(?i)([a-z\d]+:[//])([\w\-._~:/?#\[\]@!$&'()*+,;%=]+(?:(?:\.[\w_\-]+)+))([\w.,@?^=%&:/~+#\-]*[\w@?^=%&/~+#\-])"
        return re.search(link_pat, message.content) is not None
        
    elif trigger == "t:phishing":
        if not message or not message.content:
            return False
        import re
        phish_patterns = [
            r"steamcommmun[iy]ty\.com", r"free-nitro", r"gift-nitro",
            r"discord-nitro", r"nitro-gift", r"steam-gift",
            r"discorcl", r"dlscord"
        ]
        for pat in phish_patterns:
            if re.search(pat, message.content.lower()):
                return True
        return False
        
    return False

async def check_text_against_keywords(text: str, keywords: list[str], use_emoji: bool = False, use_homo: bool = False, member: discord.Member = None, message: discord.Message = None) -> bool:
    if not keywords:
        return False
        
    conditions, triggers, regular_keywords = parse_keyword_tags(keywords)
    
    # Check conditions (ALL must be met)
    if conditions:
        if not member:
            return False
        for cond in conditions:
            if not evaluate_condition(cond, member, message):
                return False
                
    # Check triggers & regular keywords (OR logic)
    matched = False
    
    # Check trigger tags (any must match)
    if triggers:
        if member:
            for trig in triggers:
                if await evaluate_trigger(trig, member, message):
                    matched = True
                    break
                    
    # Check regular keywords if not already matched
    if not matched and regular_keywords:
        spaced_str, merged_str, condensed_str = normalize_text(text)
        
        text_emoji = convert_emojis_to_text(text) if use_emoji else text
        text_homo = convert_homoglyphs_to_text(text) if use_homo else text
        text_both = convert_homoglyphs_to_text(text_emoji) if (use_emoji and use_homo) else text
        
        if use_emoji and use_homo:
            target_raw = text_both
        elif use_emoji:
            target_raw = text_emoji
        elif use_homo:
            target_raw = text_homo
        else:
            target_raw = text
            
        banned_regexes = []
        banned_plains = []
        allowed_regexes = []
        allowed_plains = []
        
        for kw in regular_keywords:
            is_allowed, is_regex, pattern_str, is_wildcard_start, is_wildcard_end = parse_keyword(kw)
            if not pattern_str:
                continue
            if is_allowed:
                if is_regex:
                    allowed_regexes.append((True, pattern_str, is_wildcard_start, is_wildcard_end))
                else:
                    allowed_plains.append((False, pattern_str, is_wildcard_start, is_wildcard_end))
            else:
                if is_regex:
                    banned_regexes.append((True, pattern_str, is_wildcard_start, is_wildcard_end))
                else:
                    banned_plains.append((False, pattern_str, is_wildcard_start, is_wildcard_end))
                    
        if use_emoji or use_homo:
            banned_regexes_byp = []
            allowed_regexes_byp = []
            for kw in regular_keywords:
                is_allowed, is_regex, pattern_str, is_wildcard_start, is_wildcard_end = parse_keyword(kw)
                if not pattern_str:
                    continue
                if is_regex:
                    pat = pattern_str
                else:
                    pat = make_bypass_regex(pattern_str, is_wildcard_start, is_wildcard_end)
                
                if is_allowed:
                    allowed_regexes_byp.append((True, pat, is_wildcard_start, is_wildcard_end))
                else:
                    banned_regexes_byp.append((True, pat, is_wildcard_start, is_wildcard_end))
                    
            if banned_regexes_byp:
                if has_unallowed_match(target_raw, banned_regexes_byp, allowed_regexes_byp):
                    matched = True
        else:
            if banned_regexes:
                if has_unallowed_match(text, banned_regexes, allowed_regexes + allowed_plains):
                    matched = True
                    
            if not matched and (banned_regexes or banned_plains):
                if has_unallowed_match(spaced_str, banned_regexes + banned_plains, allowed_regexes + allowed_plains):
                    matched = True
                    
            if not matched and banned_regexes:
                if has_unallowed_match(condensed_str, banned_regexes, allowed_regexes + allowed_plains, use_word_boundary=False):
                    matched = True
                    
            if not matched and banned_plains:
                if has_unallowed_match(merged_str, banned_plains, allowed_regexes + allowed_plains):
                    matched = True
                    
        if not matched and banned_plains:
            prepared_content = prepare_message_for_word_check(text)
            prepared_words = [pw.lower() for pw in prepared_content.split()]
            
            if use_emoji or use_homo:
                prepared_target = prepare_message_for_word_check(target_raw)
                prepared_words.extend([pw.lower() for pw in prepared_target.split()])
                
            for _, pattern_str, is_wildcard_start, is_wildcard_end in banned_plains:
                for pw in prepared_words:
                    if is_wildcard_start and is_wildcard_end:
                        if pattern_str in pw:
                            matched = True
                            break
                    elif is_wildcard_start:
                        if pw.endswith(pattern_str):
                            matched = True
                            break
                    elif is_wildcard_end:
                        if pw.startswith(pattern_str):
                            matched = True
                            break
                    else:
                        if pw == pattern_str:
                            matched = True
                            break
                if matched:
                    break
                    
    return matched

async def notify_user_privately(guild, member, filter_name, raw_content, channel, winning_filter):
    """Notify the user privately (via DM with fallback to short-lived channel message)."""
    bolded_content = bold_offending_words(raw_content, winning_filter)
    blockquote_content = "\n".join(f"> {line}" for line in bolded_content.splitlines())
    warning_msg = (
        f"Please change your original message because the last one was not following the server rules.\n\n"
        f"Your message was:\n"
        f"{blockquote_content}"
    )
    try:
        await member.send(warning_msg)
    except Exception:
        try:
            await channel.send(
                f"{member.mention} {warning_msg}",
                delete_after=30
            )
        except Exception:
            pass

async def log_automod_delete_only(guild, member, filter_name, details):
    """Log a 'Delete Message Only' violation to the global log channel."""
    cfg = get_guild_config(guild.id)
    log_ch_id = cfg.get("global_log_channel_id")
    if log_ch_id:
        log_ch = guild.get_channel(log_ch_id)
        if not log_ch:
            try:
                log_ch = await guild.fetch_channel(log_ch_id)
            except Exception:
                pass
        if log_ch:
            embed = discord.Embed(
                title="AutoMod Violation (AutoMod)",
                description=f"User {member.mention} triggered AutoMod filter `{filter_name}`.\nMessage was deleted.",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="Action Taken", value="Delete Message Only", inline=True)
            embed.add_field(name="Offending Message Preview", value=str(details[:1024] or "No preview available"), inline=False)
            try:
                await log_ch.send(embed=embed)
            except Exception:
                pass

async def log_automod_ping_mods(guild, member, filter_name, details):
    """Log a 'Delete + Alert Mods' violation and ping the moderators in the log channel."""
    cfg = get_guild_config(guild.id)
    log_ch_id = cfg.get("global_log_channel_id")
    if log_ch_id:
        log_ch = guild.get_channel(log_ch_id)
        if not log_ch:
            try:
                log_ch = await guild.fetch_channel(log_ch_id)
            except Exception:
                pass
        if log_ch:
            mod_role_id = cfg.get("mod_role_id")
            admin_role_id = cfg.get("admin_role_id")
            ping_str = ""
            if mod_role_id:
                ping_str = f"<@&{mod_role_id}> "
            elif admin_role_id:
                ping_str = f"<@&{admin_role_id}> "
            else:
                ping_str = "@here "
                
            embed = discord.Embed(
                title="AutoMod Escalation Alert",
                description=f"User {member.mention} triggered AutoMod filter `{filter_name}`.\nMessage was deleted. Moderator intervention required.",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="Action Taken", value="Delete + Log & Alert Mods", inline=True)
            embed.add_field(name="Offending Message Preview", value=str(details[:1024] or "No preview available"), inline=False)
            try:
                await log_ch.send(content=f"{ping_str}AutoMod alert triggered!", embed=embed)
            except Exception:
                pass

async def trigger_automod_warning(guild, member, filter_name, severity, details):
    """Hook into Warning Tracker module if enabled."""
    cfg = get_guild_config(guild.id)
    if not cfg.get("warning_tracker_enabled", False):
        return "Warning Tracker disabled."
        
    try:
        from warning_tracker_module import (
            make_discord_target,
            get_active_points_and_records,
            execute_moderation_action,
            add_warning_record
        )
        
        targets = [make_discord_target(member)]
        severity_points = cfg.get("warning_severity_points", {"Low": 1, "Medium": 2, "High": 3})
        points = severity_points.get(severity, 1)
        
        mode = cfg.get("warning_escalation_mode", "static")
        days = cfg.get("warning_rolling_window_days", 90)
        
        current_points, _ = await get_active_points_and_records(guild.id, targets, mode, days)
        new_total_points = current_points + points
        
        warning_ladder = cfg.get("warning_ladder", {})
        applicable_action = "None"
        highest_milestone = 0
        for pt_str, act in warning_ladder.items():
            try:
                pt = int(pt_str)
                if new_total_points >= pt and pt > highest_milestone:
                    highest_milestone = pt
                    applicable_action = act
            except ValueError:
                continue
                
        reason = f"AutoMod Violation for filter '{filter_name}': {details}"
        status_msg = await execute_moderation_action(guild, targets, applicable_action, reason, moderator="AutoMod")
        
        record = await add_warning_record(
            guild_id=guild.id,
            targets=targets,
            details=f"AutoMod Violation: Matched filter '{filter_name}'. Message content: '{details}'",
            severity=severity,
            points=points,
            action_taken=applicable_action
        )
        
        log_ch_id = cfg.get("warning_log_channel_id") or cfg.get("global_log_channel_id")
        if log_ch_id:
            channel = guild.get_channel(log_ch_id)
            if not channel:
                try:
                    channel = await guild.fetch_channel(log_ch_id)
                except Exception:
                    pass
            if channel:
                embed = discord.Embed(
                    title="Warning Event Logged (AutoMod)",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.utcnow()
                )
                embed.add_field(name="Warning ID", value=str(record.get("id") or "Unknown"), inline=True)
                embed.add_field(name="Severity", value=str(severity or "Low"), inline=True)
                embed.add_field(name="Points", value=str(points or 1), inline=True)
                embed.add_field(name="Warning Targets", value=f"Discord: {member.name} (ID: {member.id})", inline=False)
                embed.add_field(name="Details", value=str(record.get("details") or "No details"), inline=False)
                embed.add_field(name="Escalation Action Taken", value=str(applicable_action or "None"), inline=False)
                embed.set_footer(text="Moderator: AutoMod")
                try:
                    await channel.send(embed=embed)
                except Exception:
                    pass
                    
        dm_enabled = cfg.get("warning_dm_enabled", False)
        if dm_enabled:
            try:
                dm_msg = (
                    f"{guild.name} AutoMod added a warning to your account for matching filter '{filter_name}'.\n"
                    f"Action taken: {applicable_action}"
                )
                await member.send(dm_msg)
            except Exception:
                pass
                
        return f"Warning applied. Action: {applicable_action}. Status: {status_msg}"
        
    except Exception as e:
        return f"Warning Tracker error: {e}"

async def trigger_automod_direct_penalty(guild, member, filter_name, penalty, details, channel=None):
    """Execute direct penalty (Timeout/Ban) bypassing the warning counter."""
    cfg = get_guild_config(guild.id)
    action_str = penalty
    reason = f"AutoMod Direct Penalty '{penalty}' for filter '{filter_name}' violation: {details}"
    
    status_msg = "Unknown status"
    try:
        from warning_tracker_module import execute_moderation_action, make_discord_target
        targets = [make_discord_target(member)]
        status_msg = await execute_moderation_action(guild, targets, action_str, reason, moderator="AutoMod")
    except Exception as e:
        if penalty == "Permanent Ban":
            try:
                await member.ban(reason=reason)
                status_msg = "Banned natively via fallback."
            except Exception as ex:
                status_msg = f"Ban fallback failed: {ex}"
        elif penalty == "1-Hour Timeout":
            try:
                await member.timeout(datetime.timedelta(hours=1), reason=reason)
                status_msg = "Timed out natively via fallback."
            except Exception as ex:
                status_msg = f"Timeout fallback failed: {ex}"
                
    log_ch_id = cfg.get("warning_log_channel_id") or cfg.get("global_log_channel_id")
    if log_ch_id:
        log_ch = guild.get_channel(log_ch_id)
        if not log_ch:
            try:
                log_ch = await guild.fetch_channel(log_ch_id)
            except Exception:
                pass
        if log_ch:
            embed = discord.Embed(
                title="AutoMod Direct Penalty Executed",
                color=discord.Color.dark_red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="User", value=f"{member.name} (ID: {member.id})", inline=True)
            embed.add_field(name="Filter", value=filter_name, inline=True)
            embed.add_field(name="Penalty", value=penalty, inline=True)
            embed.add_field(name="Result", value=status_msg, inline=False)
            embed.add_field(name="Offending Content", value=details[:1024], inline=False)
            embed.set_footer(text="Moderator: AutoMod")
            try:
                await log_ch.send(embed=embed)
            except Exception:
                pass

async def handle_automod_message(message: discord.Message) -> bool:
    """Interception engine entrypoint hook."""
    if not message.guild or message.author.bot:
        return False
        
    cfg = get_guild_config(message.guild.id)
    if not cfg.get("automod_enabled", False):
        return False
        
    # Ignored Channels bypass
    ignored_channels = cfg.get("automod_ignored_channels", [])
    if message.channel.id in ignored_channels:
        return False
        
    # Ignored Roles bypass
    ignored_roles = cfg.get("automod_ignored_roles", [])
    if ignored_roles and isinstance(message.author, discord.Member):
        if _has_any_role(message.author, ignored_roles):
            return False
                
    raw_content = message.content
    
    filters = cfg.get("automod_filters", [])
    matched_filters = []
    
    for flt in filters:
        if not flt.get("enabled", True):
            continue
            
        # Check filter-specific ignored roles
        filter_ignored_roles = flt.get("ignored_roles", [])
        if filter_ignored_roles and isinstance(message.author, discord.Member):
            if _has_any_role(message.author, filter_ignored_roles):
                continue
            
        # Check filter-specific ignored users
        filter_ignored_users = flt.get("ignored_users", [])
        if message.author.id in filter_ignored_users:
            continue
            
        # Check filter-specific ignored channels
        filter_ignored_channels = flt.get("ignored_channels", [])
        if message.channel.id in filter_ignored_channels:
            continue
            
        keywords = flt.get("keywords", [])
        if await check_text_against_keywords(raw_content, keywords, flt.get("filter_emojis", False), flt.get("filter_homoglyphs", False), member=message.author, message=message):
            matched_filters.append(flt)
            
    if not matched_filters:
        return False
        
    # - Direct Penalty Permanent Ban = 6
    # - Direct Penalty 1-Hour Timeout = 5
    # - Warn User High = 4
    # - Warn User Medium = 3
    # - Warn User Low = 2
    # - Delete Only = 1
    def get_filter_weight(f):
        act = f.get("enforcement_action", "Delete Message Only")
        if act == "Delete + Direct Penalty":
            pen = f.get("direct_penalty", "1-Hour Timeout")
            return 6 if pen == "Permanent Ban" else 5
        elif act == "Delete + Warn User":
            sev = f.get("warning_severity", "Low")
            if sev == "High": return 4
            if sev == "Medium": return 3
            return 2
        elif act == "Delete + Alert Mods":
            return 2
        return 1
        
    matched_filters.sort(key=get_filter_weight, reverse=True)
    winning_filter = matched_filters[0]
    
    try:
        await message.delete()
    except Exception:
        pass
        
    filter_name = winning_filter.get("name", "Unknown")
    action = winning_filter.get("enforcement_action", "Delete Message Only")
    
    if action == "Delete + Warn User":
        severity = winning_filter.get("warning_severity", "Low")
        res = await trigger_automod_warning(message.guild, message.author, filter_name, severity, raw_content)
        print(f"[AutoMod Debug] trigger_automod_warning result: {res}")
        if not res.startswith("Warning applied"):
            await log_fallback_automod_violation(message.guild, message.author, filter_name, severity, raw_content, channel=message.channel)
        else:
            await notify_user_privately(message.guild, message.author, filter_name, raw_content, message.channel, winning_filter)
    elif action == "Delete + Direct Penalty":
        penalty = winning_filter.get("direct_penalty", "1-Hour Timeout")
        await trigger_automod_direct_penalty(message.guild, message.author, filter_name, penalty, raw_content, channel=message.channel)
        try:
            await message.channel.send(
                f"{message.author.mention} has been disciplined ({penalty}) for violating AutoMod filter `{filter_name}`.",
                delete_after=10
            )
        except Exception:
            pass
        await notify_user_privately(message.guild, message.author, filter_name, raw_content, message.channel, winning_filter)
    elif action == "Delete + Alert Mods":
        await log_automod_ping_mods(message.guild, message.author, filter_name, raw_content)
        await notify_user_privately(message.guild, message.author, filter_name, raw_content, message.channel, winning_filter)
    else:
        await log_automod_delete_only(message.guild, message.author, filter_name, raw_content)
        await notify_user_privately(message.guild, message.author, filter_name, raw_content, message.channel, winning_filter)
            
    return True


async def handle_automod_nickname(member: discord.Member) -> bool:
    """Check a member's nickname against enabled filters."""
    if member.bot:
        return False
        
    cfg = get_guild_config(member.guild.id)
    if not cfg.get("automod_enabled", False):
        return False
        
    # Ignored Roles bypass
    ignored_roles = cfg.get("automod_ignored_roles", [])
    if ignored_roles and _has_any_role(member, ignored_roles):
        return False
            
    nick = member.nick
    if not nick:
        return False
        
    matched_filters = []
    filters = cfg.get("automod_filters", [])
    
    for flt in filters:
        if not flt.get("enabled", True):
            continue
            
        # Check filter-specific ignored roles
        filter_ignored_roles = flt.get("ignored_roles", [])
        if filter_ignored_roles and _has_any_role(member, filter_ignored_roles):
            continue
            
        # Check filter-specific ignored users
        filter_ignored_users = flt.get("ignored_users", [])
        if member.id in filter_ignored_users:
            continue
            
        keywords = flt.get("keywords", [])
        if await check_text_against_keywords(nick, keywords, flt.get("filter_emojis", False), flt.get("filter_homoglyphs", False), member=member):
            matched_filters.append(flt)
            
    if not matched_filters:
        return False
        
    def get_filter_weight(f):
        act = f.get("enforcement_action", "Delete Message Only")
        if act == "Delete + Direct Penalty":
            pen = f.get("direct_penalty", "1-Hour Timeout")
            return 6 if pen == "Permanent Ban" else 5
        elif act == "Delete + Warn User":
            sev = f.get("warning_severity", "Low")
            if sev == "High": return 4
            if sev == "Medium": return 3
            return 2
        elif act == "Delete + Alert Mods":
            return 2
        return 1
        
    matched_filters.sort(key=get_filter_weight, reverse=True)
    winning_filter = matched_filters[0]
    filter_name = winning_filter.get("name", "Unknown")
    
    # Action taken: reset nickname first
    try:
        await member.edit(nick=None, reason=f"AutoMod Nickname Violation: {filter_name}")
    except Exception:
        pass
        
    action = winning_filter.get("enforcement_action", "Delete Message Only")
    details = f"Offending Nickname: '{nick}'"
    
    if action == "Delete + Warn User":
        severity = winning_filter.get("warning_severity", "Low")
        res = await trigger_automod_warning(member.guild, member, filter_name, severity, details)
        if not res.startswith("Warning applied"):
            await log_fallback_automod_violation(member.guild, member, filter_name, severity, details)
    elif action == "Delete + Direct Penalty":
        penalty = winning_filter.get("direct_penalty", "1-Hour Timeout")
        await trigger_automod_direct_penalty(member.guild, member, filter_name, penalty, details)
    elif action == "Delete + Alert Mods":
        await log_automod_ping_mods(member.guild, member, filter_name, details)
    else:
        await log_automod_delete_only(member.guild, member, filter_name, details)
        
    return True


async def handle_automod_join(member: discord.Member) -> bool:
    """Check a joining member's username and global name against enabled filters."""
    if member.bot:
        return False
        
    cfg = get_guild_config(member.guild.id)
    if not cfg.get("automod_enabled", False):
        return False
        
    username = member.name
    global_name = member.global_name or ""
    
    matched_filters = []
    filters = cfg.get("automod_filters", [])
    
    for flt in filters:
        if not flt.get("enabled", True):
            continue
            
        # Check filter-specific ignored users
        filter_ignored_users = flt.get("ignored_users", [])
        if member.id in filter_ignored_users:
            continue
            
        keywords = flt.get("keywords", [])
        
        if await check_text_against_keywords(username, keywords, flt.get("filter_emojis", False), flt.get("filter_homoglyphs", False), member=member):
            matched_filters.append(flt)
            continue
            
        # Check global name
        if global_name and await check_text_against_keywords(global_name, keywords, flt.get("filter_emojis", False), flt.get("filter_homoglyphs", False), member=member):
            matched_filters.append(flt)
            
    if not matched_filters:
        return False
        
    def get_filter_weight(f):
        act = f.get("enforcement_action", "Delete Message Only")
        if act == "Delete + Direct Penalty":
            pen = f.get("direct_penalty", "1-Hour Timeout")
            return 6 if pen == "Permanent Ban" else 5
        elif act == "Delete + Warn User":
            sev = f.get("warning_severity", "Low")
            if sev == "High": return 4
            if sev == "Medium": return 3
            return 2
        elif act == "Delete + Alert Mods":
            return 2
        return 1
        
    matched_filters.sort(key=get_filter_weight, reverse=True)
    winning_filter = matched_filters[0]
    filter_name = winning_filter.get("name", "Unknown")
    
    action = winning_filter.get("enforcement_action", "Delete Message Only")
    details = f"Offending Username: '{username}' | Global Name: '{global_name}'"
    
    if action == "Delete + Warn User":
        severity = winning_filter.get("warning_severity", "Low")
        res = await trigger_automod_warning(member.guild, member, filter_name, severity, details)
        if not res.startswith("Warning applied"):
            await log_fallback_automod_violation(member.guild, member, filter_name, severity, details)
    elif action == "Delete + Direct Penalty":
        penalty = winning_filter.get("direct_penalty", "1-Hour Timeout")
        await trigger_automod_direct_penalty(member.guild, member, filter_name, penalty, details)
    elif action == "Delete + Alert Mods":
        await log_automod_ping_mods(member.guild, member, filter_name, details)
    else:
        await log_automod_delete_only(member.guild, member, filter_name, details)
        
    return True


# --- UI DASHBOARDS & WIZARDS ---

class AutoModConfigDashboard(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        enabled = cfg.get("automod_enabled", False)
        filters = cfg.get("automod_filters", [])
        ignored_ch = cfg.get("automod_ignored_channels", [])
        ignored_rl = cfg.get("automod_ignored_roles", [])
        
        embed = discord.Embed(
            title="Nebot Module: Advanced AutoMod",
            description="Configure content filtration tiers, create custom keyword rules, and define automatic escalation behaviors.",
            color=discord.Color.purple()
        )
        embed.add_field(name="AutoMod Status", value="[ENABLED]" if enabled else "[DISABLED]", inline=True)
        embed.add_field(name="Filter Count", value=f"{len(filters)} registered filters", inline=True)
        
        ch_str = ", ".join(f"<#{cid}>" for cid in ignored_ch) if ignored_ch else "None"
        rl_str = ", ".join(f"<@&{rid}>" for rid in ignored_rl) if ignored_rl else "None"
        embed.add_field(name="Ignored Channels", value=ch_str, inline=False)
        embed.add_field(name="Ignored Roles", value=rl_str, inline=False)
        
        if filters:
            f_lines = []
            for f in filters[:10]: # Show up to 10 filters
                status_icon = "[ON]" if f.get("enabled", True) else "[OFF]"
                action_str = f.get("enforcement_action", "Delete Only")
                if action_str == "Delete + Warn User":
                    action_str += f" ({f.get('warning_severity', 'Low')})"
                elif action_str == "Delete + Direct Penalty":
                    action_str += f" ({f.get('direct_penalty', '1-Hour Timeout')})"
                f_lines.append(f"{status_icon} **{f.get('name')}**: {action_str} ({len(f.get('keywords', []))} keywords)")
            embed.add_field(name="Active Filters Profile", value="\n".join(f_lines), inline=False)
        else:
            embed.add_field(name="Active Filters Profile", value="No filters configured yet.", inline=False)
            
        return embed

    @ui.button(label="Toggle AutoMod", style=discord.ButtonStyle.primary, row=0)
    async def toggle_automod(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["automod_enabled"] = not cfg.get("automod_enabled", False)
        save_config()

        await configuration_module.log_setting_change(interaction.guild, interaction.user, f"Toggled AutoMod module state to `{'enabled' if cfg['automod_enabled'] else 'disabled'}`")
        await self.refresh(interaction)

    @ui.button(label="Manage Filters", style=discord.ButtonStyle.secondary, row=0)
    async def manage_filters(self, interaction: discord.Interaction, button: ui.Button):
        view = ManageFiltersView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Create Filter", style=discord.ButtonStyle.success, row=0)
    async def create_filter(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(CreateFilterModal(self.guild_id))

    @ui.button(label="Recommended Filters", style=discord.ButtonStyle.secondary, row=1)
    async def recommended_filters(self, interaction: discord.Interaction, button: ui.Button):
        view = ManageRecommendedFiltersView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Ignored Channels/Roles", style=discord.ButtonStyle.secondary, row=1)
    async def ignored_config(self, interaction: discord.Interaction, button: ui.Button):
        view = IgnoredChannelsRolesView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Back to Modules", style=discord.ButtonStyle.danger, row=1)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        from admin_ui_module import ModuleSelectView
        view = ModuleSelectView(self.guild_id)
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class RecommendedFilterSelectMenu(ui.Select):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        # Fixed indent / access to configuration_module
        recs = configuration_module.recommended_automod_filters
        
        options = []
        for idx, f in enumerate(recs[:25]):
            options.append(discord.SelectOption(
                label=f.get("name"),
                description=f"Action: {f.get('enforcement_action')} | KWs: {len(f.get('keywords', []))}",
                value=str(idx)
            ))
            
        if not options:
            options.append(discord.SelectOption(label="No recommended filters configured", value="none"))
            super().__init__(placeholder="No recommended filters available", options=options, disabled=True, row=0)
        else:
            super().__init__(placeholder="Select a recommended filter...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_index = int(self.values[0]) if self.values[0] != "none" else None
        await self.view.refresh(interaction)


class ManageRecommendedFiltersView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.selected_index = None
        self.filter_emojis = False
        self.filter_homoglyphs = False
        self.add_item(RecommendedFilterSelectMenu(guild_id))

    def build_embed(self) -> discord.Embed:
        # Fixed indent / access to configuration_module
        recs = configuration_module.recommended_automod_filters
        
        embed = discord.Embed(
            title="AutoMod: Recommended Filters",
            description="View recommended filters and add them to your active filter list.",
            color=discord.Color.purple()
        )
        
        selected_filter = None
        if self.selected_index is not None and 0 <= self.selected_index < len(recs):
            selected_filter = recs[self.selected_index]
                
        if selected_filter:
            action = selected_filter.get("enforcement_action", "Delete Message Only")
            if action == "Delete + Warn User":
                action += f" (Severity: {selected_filter.get('warning_severity', 'Low')})"
            elif action == "Delete + Direct Penalty":
                action += f" (Penalty: {selected_filter.get('direct_penalty', '1-Hour Timeout')})"
                
            kws = safe_join_items([f"`{k}`" for k in selected_filter.get("keywords", [])])
            emoji_status = "ENABLED" if self.filter_emojis else "DISABLED"
            homoglyph_status = "ENABLED" if self.filter_homoglyphs else "DISABLED"
            
            embed.add_field(name="Filter Name", value=selected_filter.get("name"), inline=True)
            embed.add_field(name="Default Action", value=action, inline=True)
            embed.add_field(name="Emoji Filter", value=emoji_status, inline=True)
            embed.add_field(name="Homoglyph Filter", value=homoglyph_status, inline=True)
            embed.add_field(name="Keywords", value=kws or "None", inline=False)
        else:
            embed.add_field(name="Details", value="Select a recommended filter from the dropdown to view its contents.", inline=False)
            
        return embed

    @ui.button(label="Add Selected Filter", style=discord.ButtonStyle.success, row=1)
    async def add_selected(self, interaction: discord.Interaction, button: ui.Button):
        if self.selected_index is None:
            return await interaction.response.send_message("Please select a recommended filter first.", ephemeral=True)
            
        # Fixed indent / access to configuration_module
        recs = configuration_module.recommended_automod_filters
        if self.selected_index < 0 or self.selected_index >= len(recs):
            return await interaction.response.send_message("Invalid selection.", ephemeral=True)
            
        selected = recs[self.selected_index]
        cfg = get_guild_config(self.guild_id)
        filters = cfg.setdefault("automod_filters", [])
        
        if any(f.get("name").lower() == selected.get("name").lower() for f in filters):
            return await interaction.response.send_message(f"A filter named '{selected.get('name')}' is already in your filter list.", ephemeral=True)
            
        new_filter = {
            "id": uuid.uuid4().hex,
            "name": selected.get("name"),
            "enabled": True,
            "keywords": list(selected.get("keywords", [])),
            "enforcement_action": selected.get("enforcement_action", "Delete Message Only"),
            "warning_severity": selected.get("warning_severity"),
            "direct_penalty": selected.get("direct_penalty"),
            "filter_emojis": self.filter_emojis,
            "filter_homoglyphs": self.filter_homoglyphs,
            "ignored_channels": [],
            "ignored_roles": [],
            "ignored_users": []
        }
        filters.append(new_filter)
        save_config()
        

        configuration_module.log_setting_change_task(interaction.guild, interaction.user, f"Added recommended AutoMod filter '{new_filter['name']}'")
        await interaction.response.send_message(f"Successfully added '{new_filter['name']}' to your filter list.", ephemeral=True)

    @ui.button(label="Add All Recommended", style=discord.ButtonStyle.primary, row=1)
    async def add_all(self, interaction: discord.Interaction, button: ui.Button):
        # Fixed indent / access to configuration_module
        recs = configuration_module.recommended_automod_filters
        if not recs:
            return await interaction.response.send_message("No recommended filters available.", ephemeral=True)
            
        cfg = get_guild_config(self.guild_id)
        filters = cfg.setdefault("automod_filters", [])
        
        added_names = []
        for rec in recs:
            if any(f.get("name").lower() == rec.get("name").lower() for f in filters):
                continue
            new_filter = {
                "id": uuid.uuid4().hex,
                "name": rec.get("name"),
                "enabled": True,
                "keywords": list(rec.get("keywords", [])),
                "enforcement_action": rec.get("enforcement_action", "Delete Message Only"),
                "warning_severity": rec.get("warning_severity"),
                "direct_penalty": rec.get("direct_penalty"),
                "filter_emojis": False,
                "filter_homoglyphs": False,
                "ignored_channels": [],
                "ignored_roles": [],
                "ignored_users": []
            }
            filters.append(new_filter)
            added_names.append(new_filter["name"])
            
        if not added_names:
            return await interaction.response.send_message("All recommended filters are already in your filter list.", ephemeral=True)
            
        save_config()

        configuration_module.log_setting_change_task(interaction.guild, interaction.user, f"Added all recommended AutoMod filters: {', '.join(added_names)}")
        await interaction.response.send_message(f"Successfully added {len(added_names)} recommended filters: {', '.join(added_names)}", ephemeral=True)

    @ui.button(label="Toggle Emoji Filter", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_emoji_filter(self, interaction: discord.Interaction, button: ui.Button):
        if self.selected_index is None:
            return await interaction.response.send_message("Please select a recommended filter first.", ephemeral=True)
        self.filter_emojis = not self.filter_emojis
        await self.refresh(interaction)

    @ui.button(label="Toggle Homoglyph Filter", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_homoglyph_filter(self, interaction: discord.Interaction, button: ui.Button):
        if self.selected_index is None:
            return await interaction.response.send_message("Please select a recommended filter first.", ephemeral=True)
        self.filter_homoglyphs = not self.filter_homoglyphs
        await self.refresh(interaction)

    @ui.button(label="Back to AutoMod Dashboard", style=discord.ButtonStyle.secondary, row=2)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = AutoModConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(embed=embed, view=dashboard)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)


# --- WIZARD: CREATE FILTER MODAL ---

class CreateFilterModal(ui.Modal, title="Create Custom Filter"):
    filter_name = ui.TextInput(label="Filter Name", placeholder="e.g. Slur Blacklist", required=True)
    keywords = ui.TextInput(
        label="Keywords (comma-separated)",
        placeholder="Use *word* for wildcards, r: for regex, a: for allowed (e.g. *bad*, r:phish.*, a:grape)",
        style=discord.TextStyle.paragraph,
        required=True
    )

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        name = self.filter_name.value.strip()
        kws = [k.strip() for k in self.keywords.value.split(",") if k.strip()]
        
        # Next wizard step: Select Enforcement Action
        view = EnforcementActionSelectionView(self.guild_id, name, kws)
        embed = discord.Embed(
            title="Create Filter: Enforcement Action",
            description=f"Configure the disciplinary action to take when a message matches **{name}**.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class EnforcementActionSelectionView(ui.View):
    def __init__(self, guild_id: int, name: str, keywords: list[str]):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.name = name
        self.keywords = keywords

    @ui.button(label="Delete Message Only", style=discord.ButtonStyle.primary)
    async def delete_only(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter(interaction.user, "Delete Message Only")
        await self.finish(interaction)

    @ui.button(label="Delete + Warn User", style=discord.ButtonStyle.secondary)
    async def delete_warn(self, interaction: discord.Interaction, button: ui.Button):
        # Next step: Severity
        view = SelectSeverityView(self.guild_id, self.name, self.keywords)
        embed = discord.Embed(title="Create Filter: Warning Severity", description="Select the warning severity points to assign.", color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Delete + Direct Penalty", style=discord.ButtonStyle.danger)
    async def delete_direct(self, interaction: discord.Interaction, button: ui.Button):
        # Next step: Penalty
        view = SelectPenaltyView(self.guild_id, self.name, self.keywords)
        embed = discord.Embed(title="Create Filter: Direct Penalty", description="Select the immediate native penalty to apply.", color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Delete + Alert Mods", style=discord.ButtonStyle.secondary)
    async def delete_alert_mods(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter(interaction.user, "Delete + Alert Mods")
        await self.finish(interaction)

    def save_filter(self, user, action: str, severity: str = None, penalty: str = None):
        cfg = get_guild_config(self.guild_id)
        filters = cfg.setdefault("automod_filters", [])
        filters.append({
            "id": uuid.uuid4().hex,
            "name": self.name,
            "enabled": True,
            "keywords": self.keywords,
            "enforcement_action": action,
            "warning_severity": severity,
            "direct_penalty": penalty,
            "filter_emojis": False,
            "filter_homoglyphs": False,
            "ignored_channels": [],
            "ignored_roles": [],
            "ignored_users": []
        })
        save_config()

        configuration_module.log_setting_change_task(user.guild, user, f"Created AutoMod filter `{self.name}` with enforcement action `{action}`")

    async def finish(self, interaction: discord.Interaction):
        # Return to main dashboard (need to edit root config message)
        dashboard = AutoModConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        # Ephemeral confirmation, then delete or update
        await interaction.response.edit_message(content="Filter created successfully!", embed=None, view=None)


class SelectSeverityView(ui.View):
    def __init__(self, guild_id: int, name: str, keywords: list[str]):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.name = name
        self.keywords = keywords

    @ui.button(label="Low Severity", style=discord.ButtonStyle.secondary)
    async def low_sev(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter(interaction.user, "Low")
        await self.finish(interaction)

    @ui.button(label="Medium Severity", style=discord.ButtonStyle.primary)
    async def med_sev(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter(interaction.user, "Medium")
        await self.finish(interaction)

    @ui.button(label="High Severity", style=discord.ButtonStyle.danger)
    async def high_sev(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter(interaction.user, "High")
        await self.finish(interaction)

    def save_filter(self, user, severity: str):
        cfg = get_guild_config(self.guild_id)
        filters = cfg.setdefault("automod_filters", [])
        filters.append({
            "id": uuid.uuid4().hex,
            "name": self.name,
            "enabled": True,
            "keywords": self.keywords,
            "enforcement_action": "Delete + Warn User",
            "warning_severity": severity,
            "direct_penalty": None,
            "ignored_channels": [],
            "ignored_roles": [],
            "ignored_users": []
        })
        save_config()

        configuration_module.log_setting_change_task(user.guild, user, f"Created AutoMod filter `{self.name}` with enforcement action `Delete + Warn User ({severity} Severity)`")

    async def finish(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Filter created successfully!", embed=None, view=None)


class SelectPenaltyView(ui.View):
    def __init__(self, guild_id: int, name: str, keywords: list[str]):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.name = name
        self.keywords = keywords

    @ui.button(label="1-Hour Timeout", style=discord.ButtonStyle.secondary)
    async def timeout_penalty(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter(interaction.user, "1-Hour Timeout")
        await self.finish(interaction)

    @ui.button(label="Permanent Ban", style=discord.ButtonStyle.danger)
    async def ban_penalty(self, interaction: discord.Interaction, button: ui.Button):
        self.save_filter(interaction.user, "Permanent Ban")
        await self.finish(interaction)

    def save_filter(self, user, penalty: str):
        cfg = get_guild_config(self.guild_id)
        filters = cfg.setdefault("automod_filters", [])
        filters.append({
            "id": uuid.uuid4().hex,
            "name": self.name,
            "enabled": True,
            "keywords": self.keywords,
            "enforcement_action": "Delete + Direct Penalty",
            "warning_severity": None,
            "direct_penalty": penalty,
            "ignored_channels": [],
            "ignored_roles": [],
            "ignored_users": []
        })
        save_config()

        configuration_module.log_setting_change_task(user.guild, user, f"Created AutoMod filter `{self.name}` with enforcement action `Delete + Direct Penalty ({penalty})`")

    async def finish(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Filter created successfully!", embed=None, view=None)


# --- MANAGE FILTERS VIEW ---

class FilterSelectMenu(ui.Select):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        cfg = get_guild_config(guild_id)
        filters = cfg.get("automod_filters", [])
        
        options = []
        for f in filters[:25]:
            status_str = "Enabled" if f.get("enabled", True) else "Disabled"
            options.append(discord.SelectOption(
                label=f.get("name"),
                description=f"Status: {status_str} | KWs: {len(f.get('keywords', []))}",
                value=f.get("id")
            ))
            
        if not options:
            options.append(discord.SelectOption(label="No filters configured", value="none"))
            super().__init__(placeholder="No filters available", options=options, disabled=True, row=0)
        else:
            super().__init__(placeholder="Select a filter profile...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        # Update view active selection
        self.view.selected_filter_id = self.values[0]
        await self.view.refresh(interaction)


class ManageFiltersView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.selected_filter_id = None
        self.add_item(FilterSelectMenu(guild_id))

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        filters = cfg.get("automod_filters", [])
        
        embed = discord.Embed(
            title="AutoMod: Manage Filters",
            description="View details, toggle, or delete existing filters.",
            color=discord.Color.purple()
        )
        
        selected_filter = None
        for f in filters:
            if f.get("id") == self.selected_filter_id:
                selected_filter = f
                break
                
        if selected_filter:
            status = "ENABLED" if selected_filter.get("enabled", True) else "DISABLED"
            emoji_status = "ENABLED" if selected_filter.get("filter_emojis", False) else "DISABLED"
            homoglyph_status = "ENABLED" if selected_filter.get("filter_homoglyphs", False) else "DISABLED"
            action = selected_filter.get("enforcement_action", "Delete Message Only")
            if action == "Delete + Warn User":
                action += f" (Severity: {selected_filter.get('warning_severity', 'Low')})"
            elif action == "Delete + Direct Penalty":
                action += f" (Penalty: {selected_filter.get('direct_penalty', '1-Hour Timeout')})"
                
            kws = safe_join_items([f"`{k}`" for k in selected_filter.get("keywords", [])])
            ignored_ch = selected_filter.get("ignored_channels", [])
            ignored_rl = selected_filter.get("ignored_roles", [])
            ignored_us = selected_filter.get("ignored_users", [])
            
            ch_str = safe_join_items([f"<#{cid}>" for cid in ignored_ch])
            rl_str = safe_join_items([f"<@&{rid}>" for rid in ignored_rl])
            us_str = safe_join_items([f"<@{uid}>" for uid in ignored_us])
            
            embed.add_field(name="Filter Name", value=selected_filter.get("name"), inline=True)
            embed.add_field(name="Status", value=status, inline=True)
            embed.add_field(name="Emoji Filter", value=emoji_status, inline=True)
            embed.add_field(name="Homoglyph Filter", value=homoglyph_status, inline=True)
            embed.add_field(name="Action", value=action, inline=False)
            embed.add_field(name="Keywords", value=kws or "None", inline=False)
            embed.add_field(name="Exempt Channels", value=ch_str, inline=True)
            embed.add_field(name="Exempt Roles", value=rl_str, inline=True)
            embed.add_field(name="Exempt Users", value=us_str, inline=True)
        else:
            embed.add_field(name="Details", value="Please select a filter profile from the dropdown menu to manage it.", inline=False)
            
        return embed

    @ui.button(label="Toggle Status", style=discord.ButtonStyle.primary, row=1)
    async def toggle_status(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_filter_id:
            return await interaction.response.send_message("Please select a filter first.", ephemeral=True)
            
        cfg = get_guild_config(self.guild_id)
        filter_name = "Unknown"
        new_status = False
        for f in cfg.get("automod_filters", []):
            if f.get("id") == self.selected_filter_id:
                f["enabled"] = not f.get("enabled", True)
                filter_name = f.get("name", "Unknown")
                new_status = f["enabled"]
                break
        save_config()

        await configuration_module.log_setting_change(interaction.guild, interaction.user, f"Toggled status of AutoMod filter `{filter_name}` to `{'enabled' if new_status else 'disabled'}`")
        
        view = ManageFiltersView(self.guild_id)
        view.selected_filter_id = self.selected_filter_id
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Edit Keywords", style=discord.ButtonStyle.secondary, row=1)
    async def edit_keywords(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_filter_id:
            return await interaction.response.send_message("Please select a filter first.", ephemeral=True)
            
        cfg = get_guild_config(self.guild_id)
        selected_filter = None
        for f in cfg.get("automod_filters", []):
            if f.get("id") == self.selected_filter_id:
                selected_filter = f
                break
        if not selected_filter:
            return await interaction.response.send_message("Filter not found.", ephemeral=True)
            
        await interaction.response.send_modal(EditKeywordsModal(self.guild_id, self.selected_filter_id, selected_filter.get("keywords", [])))

    @ui.button(label="Delete Filter", style=discord.ButtonStyle.danger, row=1)
    async def delete_filter(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_filter_id:
            return await interaction.response.send_message("Please select a filter first.", ephemeral=True)
            
        cfg = get_guild_config(self.guild_id)
        filters = cfg.get("automod_filters", [])
        filter_name = "Unknown"
        for i, f in enumerate(filters):
            if f.get("id") == self.selected_filter_id:
                filter_name = f.get("name", "Unknown")
                filters.pop(i)
                break
        save_config()

        await configuration_module.log_setting_change(interaction.guild, interaction.user, f"Deleted AutoMod filter `{filter_name}`")
        
        view = ManageFiltersView(self.guild_id)
        view.selected_filter_id = None
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Edit Action", style=discord.ButtonStyle.secondary, row=2)
    async def edit_action(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_filter_id:
            return await interaction.response.send_message("Please select a filter first.", ephemeral=True)
            
        view = EditEnforcementActionView(self.guild_id, self.selected_filter_id)
        embed = discord.Embed(
            title="Edit Filter: Enforcement Action",
            description="Configure the disciplinary action to take when a message matches this filter.",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Filter Exclusions", style=discord.ButtonStyle.secondary, row=2)
    async def edit_exclusions(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_filter_id:
            return await interaction.response.send_message("Please select a filter first.", ephemeral=True)
            
        view = FilterExclusionsView(self.guild_id, self.selected_filter_id)
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Toggle Emoji Filter", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_emoji_filter(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_filter_id:
            return await interaction.response.send_message("Please select a filter first.", ephemeral=True)
            
        cfg = get_guild_config(self.guild_id)
        filter_name = "Unknown"
        new_status = False
        for f in cfg.get("automod_filters", []):
            if f.get("id") == self.selected_filter_id:
                f["filter_emojis"] = not f.get("filter_emojis", False)
                filter_name = f.get("name", "Unknown")
                new_status = f["filter_emojis"]
                break
        save_config()

        await configuration_module.log_setting_change(interaction.guild, interaction.user, f"Toggled emoji filtering of AutoMod filter `{filter_name}` to `{'enabled' if new_status else 'disabled'}`")
        
        view = ManageFiltersView(self.guild_id)
        view.selected_filter_id = self.selected_filter_id
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Toggle Homoglyph Filter", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_homoglyph_filter(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_filter_id:
            return await interaction.response.send_message("Please select a filter first.", ephemeral=True)
            
        cfg = get_guild_config(self.guild_id)
        filter_name = "Unknown"
        new_status = False
        for f in cfg.get("automod_filters", []):
            if f.get("id") == self.selected_filter_id:
                f["filter_homoglyphs"] = not f.get("filter_homoglyphs", False)
                filter_name = f.get("name", "Unknown")
                new_status = f["filter_homoglyphs"]
                break
        save_config()

        await configuration_module.log_setting_change(interaction.guild, interaction.user, f"Toggled homoglyph filtering of AutoMod filter `{filter_name}` to `{'enabled' if new_status else 'disabled'}`")
        
        view = ManageFiltersView(self.guild_id)
        view.selected_filter_id = self.selected_filter_id
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Back to AutoMod Dashboard", style=discord.ButtonStyle.secondary, row=2)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = AutoModConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(embed=embed, view=dashboard)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class EditKeywordsModal(ui.Modal, title="Edit Keywords"):
    def __init__(self, guild_id: int, filter_id: str, current_kws: list[str]):
        super().__init__()
        self.guild_id = guild_id
        self.filter_id = filter_id
        self.keywords_input = ui.TextInput(
            label="Keywords (comma-separated)",
            default=", ".join(current_kws),
            placeholder="Use *word* for wildcards, r: for regex, a: for allowed (e.g. *bad*, r:phish.*, a:grape)",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.keywords_input)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        filter_name = "Unknown"
        new_kws = []
        for f in cfg.get("automod_filters", []):
            if f.get("id") == self.filter_id:
                f["keywords"] = [k.strip() for k in self.keywords_input.value.split(",") if k.strip()]
                filter_name = f.get("name", "Unknown")
                new_kws = f["keywords"]
                break
        save_config()

        await configuration_module.log_setting_change(interaction.guild, interaction.user, f"Updated keywords for AutoMod filter `{filter_name}` to: {', '.join(new_kws)}")
        
        view = ManageFiltersView(self.guild_id)
        view.selected_filter_id = self.filter_id
        embed = view.build_embed()
        await interaction.response.edit_message(content="Keywords updated successfully!", embed=embed, view=view)


class EditEnforcementActionView(ui.View):
    def __init__(self, guild_id: int, filter_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.filter_id = filter_id

    @ui.button(label="Delete Message Only", style=discord.ButtonStyle.primary)
    async def delete_only(self, interaction: discord.Interaction, button: ui.Button):
        self.update_action(interaction.user, "Delete Message Only")
        await self.finish(interaction)

    @ui.button(label="Delete + Warn User", style=discord.ButtonStyle.secondary)
    async def delete_warn(self, interaction: discord.Interaction, button: ui.Button):
        view = EditSelectSeverityView(self.guild_id, self.filter_id)
        embed = discord.Embed(title="Edit Filter: Warning Severity", description="Select the warning severity points to assign.", color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Delete + Direct Penalty", style=discord.ButtonStyle.danger)
    async def delete_direct(self, interaction: discord.Interaction, button: ui.Button):
        view = EditSelectPenaltyView(self.guild_id, self.filter_id)
        embed = discord.Embed(title="Edit Filter: Direct Penalty", description="Select the immediate native penalty to apply.", color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Delete + Alert Mods", style=discord.ButtonStyle.secondary)
    async def delete_alert_mods(self, interaction: discord.Interaction, button: ui.Button):
        self.update_action(interaction.user, "Delete + Alert Mods")
        await self.finish(interaction)

    def update_action(self, user, action: str, severity: str = None, penalty: str = None):
        cfg = get_guild_config(self.guild_id)
        for f in cfg.get("automod_filters", []):
            if f.get("id") == self.filter_id:
                f["enforcement_action"] = action
                f["warning_severity"] = severity
                f["direct_penalty"] = penalty
                save_config()

                configuration_module.log_setting_change_task(user.guild, user, f"Updated enforcement action for AutoMod filter `{f.get('name')}` to `{action}`")
                break

    async def finish(self, interaction: discord.Interaction):
        view = ManageFiltersView(self.guild_id)
        view.selected_filter_id = self.filter_id
        embed = view.build_embed()
        await interaction.response.edit_message(content="Enforcement action updated successfully!", embed=embed, view=view)


class EditSelectSeverityView(ui.View):
    def __init__(self, guild_id: int, filter_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.filter_id = filter_id

    @ui.button(label="Low Severity", style=discord.ButtonStyle.secondary)
    async def low_sev(self, interaction: discord.Interaction, button: ui.Button):
        self.update_severity(interaction.user, "Low")
        await self.finish(interaction)

    @ui.button(label="Medium Severity", style=discord.ButtonStyle.primary)
    async def med_sev(self, interaction: discord.Interaction, button: ui.Button):
        self.update_severity(interaction.user, "Medium")
        await self.finish(interaction)

    @ui.button(label="High Severity", style=discord.ButtonStyle.danger)
    async def high_sev(self, interaction: discord.Interaction, button: ui.Button):
        self.update_severity(interaction.user, "High")
        await self.finish(interaction)

    def update_severity(self, user, severity: str):
        cfg = get_guild_config(self.guild_id)
        for f in cfg.get("automod_filters", []):
            if f.get("id") == self.filter_id:
                f["enforcement_action"] = "Delete + Warn User"
                f["warning_severity"] = severity
                f["direct_penalty"] = None
                save_config()

                configuration_module.log_setting_change_task(user.guild, user, f"Updated AutoMod filter `{f.get('name')}` enforcement action to `Delete + Warn User ({severity} Severity)`")
                break

    async def finish(self, interaction: discord.Interaction):
        view = ManageFiltersView(self.guild_id)
        view.selected_filter_id = self.filter_id
        embed = view.build_embed()
        await interaction.response.edit_message(content="Warning severity updated successfully!", embed=embed, view=view)


class EditSelectPenaltyView(ui.View):
    def __init__(self, guild_id: int, filter_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.filter_id = filter_id

    @ui.button(label="1-Hour Timeout", style=discord.ButtonStyle.secondary)
    async def timeout_penalty(self, interaction: discord.Interaction, button: ui.Button):
        self.update_penalty(interaction.user, "1-Hour Timeout")
        await self.finish(interaction)

    @ui.button(label="Permanent Ban", style=discord.ButtonStyle.danger)
    async def ban_penalty(self, interaction: discord.Interaction, button: ui.Button):
        self.update_penalty(interaction.user, "Permanent Ban")
        await self.finish(interaction)

    def update_penalty(self, user, penalty: str):
        cfg = get_guild_config(self.guild_id)
        for f in cfg.get("automod_filters", []):
            if f.get("id") == self.filter_id:
                f["enforcement_action"] = "Delete + Direct Penalty"
                f["warning_severity"] = None
                f["direct_penalty"] = penalty
                save_config()

                configuration_module.log_setting_change_task(user.guild, user, f"Updated AutoMod filter `{f.get('name')}` enforcement action to `Delete + Direct Penalty ({penalty})`")
                break

    async def finish(self, interaction: discord.Interaction):
        view = ManageFiltersView(self.guild_id)
        view.selected_filter_id = self.filter_id
        embed = view.build_embed()
        await interaction.response.edit_message(content="Direct penalty updated successfully!", embed=embed, view=view)


# --- EXCLUSIONS / BYPASS BY CHANNEL OR ROLE ---

class IgnoredChannelsSelect(discord.ui.ChannelSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Select ignored channels...", min_values=1, max_values=10, channel_types=[discord.ChannelType.text], row=1)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        cfg["automod_ignored_channels"] = [c.id for c in self.values]
        save_config()

        ch_names = ", ".join(c.name for c in self.values)
        await configuration_module.log_setting_change(interaction.guild, interaction.user, f"Updated global AutoMod ignored channels to: {ch_names}")
        await self.view.refresh(interaction)


class IgnoredRolesSelect(discord.ui.RoleSelect):
    def __init__(self, guild_id: int):
        super().__init__(placeholder="Select ignored roles...", min_values=1, max_values=10, row=2)
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        cfg["automod_ignored_roles"] = [r.id for r in self.values]
        save_config()

        role_names = ", ".join(r.name for r in self.values)
        await configuration_module.log_setting_change(interaction.guild, interaction.user, f"Updated global AutoMod ignored roles to: {role_names}")
        await self.view.refresh(interaction)


class IgnoredChannelsRolesView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(IgnoredChannelsSelect(guild_id))
        self.add_item(IgnoredRolesSelect(guild_id))

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        ignored_ch = cfg.get("automod_ignored_channels", [])
        ignored_rl = cfg.get("automod_ignored_roles", [])
        
        embed = discord.Embed(
            title="AutoMod: Channel/Role Ignored Exclusions",
            description="Configure channels and roles that are completely exempt from AutoMod content filtering.",
            color=discord.Color.purple()
        )
        ch_str = ", ".join(f"<#{cid}>" for cid in ignored_ch) if ignored_ch else "None"
        rl_str = ", ".join(f"<@&{rid}>" for rid in ignored_rl) if ignored_rl else "None"
        embed.add_field(name="Current Ignored Channels", value=ch_str, inline=False)
        embed.add_field(name="Current Ignored Roles", value=rl_str, inline=False)
        return embed

    @ui.button(label="Clear Exclusions", style=discord.ButtonStyle.secondary, row=0)
    async def clear_exclusions(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        cfg["automod_ignored_channels"] = []
        cfg["automod_ignored_roles"] = []
        save_config()

        await configuration_module.log_setting_change(interaction.guild, interaction.user, "Cleared all global AutoMod channel/role exclusions")
        await self.refresh(interaction)

    @ui.button(label="Back to AutoMod Dashboard", style=discord.ButtonStyle.danger, row=0)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = AutoModConfigDashboard(self.guild_id)
        embed = dashboard.build_embed()
        await interaction.response.edit_message(embed=embed, view=dashboard)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class FilterChannelsSelect(discord.ui.ChannelSelect):
    def __init__(self, guild_id: int, filter_id: str):
        super().__init__(placeholder="Select ignored channels for this filter...", min_values=1, max_values=10, channel_types=[discord.ChannelType.text], row=1)
        self.guild_id = guild_id
        self.filter_id = filter_id

    async def callback(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        filter_name = "Unknown"
        for f in cfg.get("automod_filters", []):
            if f.get("id") == self.filter_id:
                f["ignored_channels"] = [c.id for c in self.values]
                filter_name = f.get("name", "Unknown")
                break
        save_config()

        ch_names = ", ".join(c.name for c in self.values)
        await configuration_module.log_setting_change(interaction.guild, interaction.user, f"Updated exempt channels for filter `{filter_name}` to: {ch_names}")
        await self.view.refresh(interaction)


class FilterRolesSelect(discord.ui.RoleSelect):
    def __init__(self, guild_id: int, filter_id: str):
        super().__init__(placeholder="Select ignored roles for this filter...", min_values=1, max_values=10, row=2)
        self.guild_id = guild_id
        self.filter_id = filter_id

    async def callback(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        filter_name = "Unknown"
        for f in cfg.get("automod_filters", []):
            if f.get("id") == self.filter_id:
                f["ignored_roles"] = [r.id for r in self.values]
                filter_name = f.get("name", "Unknown")
                break
        save_config()

        role_names = ", ".join(r.name for r in self.values)
        await configuration_module.log_setting_change(interaction.guild, interaction.user, f"Updated exempt roles for filter `{filter_name}` to: {role_names}")
        await self.view.refresh(interaction)


class FilterUsersSelect(discord.ui.UserSelect):
    def __init__(self, guild_id: int, filter_id: str):
        super().__init__(placeholder="Select ignored users for this filter...", min_values=1, max_values=10, row=3)
        self.guild_id = guild_id
        self.filter_id = filter_id

    async def callback(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        filter_name = "Unknown"
        for f in cfg.get("automod_filters", []):
            if f.get("id") == self.filter_id:
                f["ignored_users"] = [u.id for u in self.values]
                filter_name = f.get("name", "Unknown")
                break
        save_config()

        user_names = ", ".join(u.name for u in self.values)
        await configuration_module.log_setting_change(interaction.guild, interaction.user, f"Updated exempt users for filter `{filter_name}` to: {user_names}")
        await self.view.refresh(interaction)


class FilterExclusionsView(ui.View):
    def __init__(self, guild_id: int, filter_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.filter_id = filter_id
        self.add_item(FilterChannelsSelect(guild_id, filter_id))
        self.add_item(FilterRolesSelect(guild_id, filter_id))
        self.add_item(FilterUsersSelect(guild_id, filter_id))

    def build_embed(self) -> discord.Embed:
        cfg = get_guild_config(self.guild_id)
        filters = cfg.get("automod_filters", [])
        selected_filter = next((f for f in filters if f.get("id") == self.filter_id), None)
        
        embed = discord.Embed(
            title=f"Filter Exclusions: {selected_filter.get('name') if selected_filter else 'Unknown'}",
            description="Configure channels, roles and users that are completely exempt from this specific filter.",
            color=discord.Color.purple()
        )
        
        ignored_ch = selected_filter.get("ignored_channels", []) if selected_filter else []
        ignored_rl = selected_filter.get("ignored_roles", []) if selected_filter else []
        ignored_us = selected_filter.get("ignored_users", []) if selected_filter else []
        
        ch_str = ", ".join(f"<#{cid}>" for cid in ignored_ch) if ignored_ch else "None"
        rl_str = ", ".join(f"<@&{rid}>" for rid in ignored_rl) if ignored_rl else "None"
        us_str = ", ".join(f"<@{uid}>" for uid in ignored_us) if ignored_us else "None"
        
        embed.add_field(name="Ignored Channels", value=ch_str, inline=False)
        embed.add_field(name="Ignored Roles", value=rl_str, inline=False)
        embed.add_field(name="Ignored Users", value=us_str, inline=False)
        return embed

    @ui.button(label="Clear Exclusions", style=discord.ButtonStyle.secondary, row=0)
    async def clear_exclusions(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_guild_config(self.guild_id)
        filter_name = "Unknown"
        for f in cfg.get("automod_filters", []):
            if f.get("id") == self.filter_id:
                f["ignored_channels"] = []
                f["ignored_roles"] = []
                f["ignored_users"] = []
                filter_name = f.get("name", "Unknown")
                break
        save_config()

        await configuration_module.log_setting_change(interaction.guild, interaction.user, f"Cleared all exclusions for filter `{filter_name}`")
        await self.refresh(interaction)

    @ui.button(label="Back to Filter Manager", style=discord.ButtonStyle.danger, row=0)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        view = ManageFiltersView(self.guild_id)
        view.selected_filter_id = self.filter_id
        embed = view.build_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)
