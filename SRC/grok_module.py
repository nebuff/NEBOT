import re
import random
import discord

# Regular expression to match "@grok" with word boundaries to avoid false positives (like "@grokking")
TRIGGER_REGEX = re.compile(r"@grok\b", re.IGNORECASE)

# Regular expression to match variations of "is this true?" possibly repeated multiple times
IS_THIS_TRUE_REGEX = re.compile(r"^\s*(?:is\s+this\s+true\s*[\?\!\.,]*\s*)+$", re.IGNORECASE)

# Response lists (strictly NO EMOJIS EVER)
REPLIES_IS_THIS_TRUE = [
    "Yes it is!",
    "Absolutely not, do not believe the rumors.",
    "According to my calculations, yes, but only if you believe hard enough.",
    "It is as true as a three-dollar bill.",
    "Big if true, but highly doubtful.",
    "Yes, and anyone who says otherwise is living in a simulation.",
    "Indeed, the truth is out there.",
    "Yes, but I had to sign an NDA to confirm it.",
    "Without a shadow of a doubt.",
    "My sources (which I made up) confirm it."
]

REPLIES_67 = [
    "67 is just two steps away from perfection, but you failed.",
    "67? A prime number of disappointment.",
    "67 is not the answer, but at least it is not 68.",
    "Why 67? Did you run out of other numbers?",
    "67 is the speed at which I ignore your questions.",
    "67 is just 69 after taxes and inflation.",
    "The number 67 has been classified as classified.",
    "Warning: 67 is highly unstable in this server."
]

REPLIES_NUMBERS = [
    "Numbers are just letters that gave up.",
    "That number has been flagged for suspicious behavior.",
    "I only calculate in binary, so that number means nothing to me.",
    "Congratulations, you found a number.",
    "My math module is offline. Please use your fingers.",
    "Dividing by that number would break the universe.",
    "A solid number, but not the winning one.",
    "That number is not in service. Please try again later."
]

REPLIES_QUESTIONS = [
    "I could tell you, but then I would have to format my hard drive.",
    "That is classified information, even for an AI.",
    "The answer is hidden behind a paywall.",
    "Have you tried turning your brain off and on again?",
    "I will answer that when humans stop arguing on the internet.",
    "My database is currently ignoring you.",
    "That query is too smart for this channel.",
    "Ask again when you have more RAM.",
    "The stars say yes, but my code says no.",
    "I checked the cosmic database, and it says: check back later."
]

REPLIES_GENERAL = [
    "I am grokking at maximum capacity and still cannot find who asked.",
    "Your message has been received and promptly ignored.",
    "I am a joke module, but you are the real punchline here.",
    "Error: User is being too serious. Initiating sarcasm protocols.",
    "I would agree with you, but then we would both be wrong.",
    "I think, therefore I am. You type, therefore you are bored.",
    "My neural network is currently running a screensaver.",
    "That is a very interesting opinion. I will store it in the recycle bin.",
    "Go grok yourself.",
    "Please limit your grokking to once per hour.",
    "I was programmed to be sarcastic, and you are making it too easy.",
    "That is nice. Anyway, moving on."
]

def contains_emoji(text: str) -> bool:
    """Check if a string contains any standard Unicode emoji or Discord custom emoji."""
    # Check for Discord custom emoji pattern: <:name:id> or <a:name:id>
    if re.search(r"<a?:\w+:\d+>", text):
        return True
        
    for char in text:
        o = ord(char)
        # Check standard Unicode emoji ranges
        if (0x1F300 <= o <= 0x1F5FF or
            0x1F600 <= o <= 0x1F64F or
            0x1F680 <= o <= 0x1F6FF or
            0x1F900 <= o <= 0x1F9FF or
            0x1FA70 <= o <= 0x1FAFF or
            0x2600 <= o <= 0x26FF or
            0x2700 <= o <= 0x27BF or
            0x1F1E6 <= o <= 0x1F1FF):
            return True
    return False

# Self-validation at import time to ensure no emojis exist in reply lists
for category_name, reply_list in [
    ("REPLIES_IS_THIS_TRUE", REPLIES_IS_THIS_TRUE),
    ("REPLIES_67", REPLIES_67),
    ("REPLIES_NUMBERS", REPLIES_NUMBERS),
    ("REPLIES_QUESTIONS", REPLIES_QUESTIONS),
    ("REPLIES_GENERAL", REPLIES_GENERAL)
]:
    for reply in reply_list:
        if contains_emoji(reply):
            raise AssertionError(f"Emoji detected in @grok joke module response under {category_name}: '{reply}'")

async def handle_grok_message(message: discord.Message) -> bool:
    """
    Intercepts messages containing or starting with @grok and replies with a joke response.
    Returns True if handled, otherwise False.
    """
    if message.author.bot:
        return False

    content = message.content
    match = TRIGGER_REGEX.search(content)
    if not match:
        return False

    # Extract the query by removing the trigger pattern from the message
    start, end = match.span()
    query = (content[:start] + " " + content[end:]).strip()

    # Determine response based on the query type
    if not query:
        response = random.choice(REPLIES_GENERAL)
    elif IS_THIS_TRUE_REGEX.match(query):
        response = random.choice(REPLIES_IS_THIS_TRUE)
    elif query == "67":
        response = random.choice(REPLIES_67)
    elif query.isdigit():
        response = random.choice(REPLIES_NUMBERS)
    elif query.endswith("?"):
        response = random.choice(REPLIES_QUESTIONS)
    else:
        response = random.choice(REPLIES_GENERAL)

    # Safety check to enforce NO EMOJIS EVER at runtime
    if contains_emoji(response):
        # Fallback to an extremely plain ASCII joke response that we know is emoji-free
        response = "I would tell a joke here, but my emoji filter blocked it."

    try:
        await message.channel.send(response)
    except Exception as ex:
        print(f"[ERROR] Failed to send @grok response: {ex}")

    return True
