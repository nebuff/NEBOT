package fun

import (
	"context"
	"log/slog"
	"math/rand/v2"
	"regexp"
	"strings"
	"unicode"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/module"
)

var (
	grokTrigger = regexp.MustCompile(`(?i)@grok\b`)
	isThisTrue  = regexp.MustCompile(`(?i)^\s*(?:is\s+this\s+true\s*[?!.,]*\s*)+$`)
	customEmoji = regexp.MustCompile(`<a?:\w+:\d+>`)
)

var (
	repliesIsThisTrue = []string{
		"Yes it is!",
		"Absolutely not, do not believe the rumors.",
		"According to my calculations, yes, but only if you believe hard enough.",
		"It is as true as a three-dollar bill.",
		"Big if true, but highly doubtful.",
		"Yes, and anyone who says otherwise is living in a simulation.",
		"Indeed, the truth is out there.",
		"Yes, but I had to sign an NDA to confirm it.",
		"Without a shadow of a doubt.",
		"My sources (which I made up) confirm it.",
	}

	replies67 = []string{
		"67 is just two steps away from perfection, but you failed.",
		"67? A prime number of disappointment.",
		"67 is not the answer, but at least it is not 68.",
		"Why 67? Did you run out of other numbers?",
		"67 is the speed at which I ignore your questions.",
		"67 is just 69 after taxes and inflation.",
		"The number 67 has been classified as classified.",
		"Warning: 67 is highly unstable in this server.",
	}

	repliesNumbers = []string{
		"Numbers are just letters that gave up.",
		"That number has been flagged for suspicious behavior.",
		"I only calculate in binary, so that number means nothing to me.",
		"Congratulations, you found a number.",
		"My math module is offline. Please use your fingers.",
		"Dividing by that number would break the universe.",
		"A solid number, but not the winning one.",
		"That number is not in service. Please try again later.",
	}

	repliesQuestions = []string{
		"I could tell you, but then I would have to format my hard drive.",
		"That is classified information, even for an AI.",
		"The answer is hidden behind a paywall.",
		"Have you tried turning your brain off and on again?",
		"I will answer that when humans stop arguing on the internet.",
		"My database is currently ignoring you.",
		"That query is too smart for this channel.",
		"Ask again when you have more RAM.",
		"The stars say yes, but my code says no.",
		"I checked the cosmic database, and it says: check back later.",
	}

	repliesGeneral = []string{
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
		"That is nice. Anyway, moving on.",
	}
)

const emojiFallback = "I would tell a joke here, but my emoji filter blocked it."

// Grok replies to messages containing "@grok" with a category-appropriate joke.
type Grok struct {
	module.Base
	log  *slog.Logger
	pick func(int) int
}

// NewGrok creates the @grok module.
func NewGrok(log *slog.Logger) *Grok {
	if log == nil {
		log = slog.Default()
	}
	return &Grok{log: log, pick: rand.IntN}
}

// Name implements module.Module.
func (m *Grok) Name() string { return "grok" }

// HandleMessage implements module.Module.
func (m *Grok) HandleMessage(_ context.Context, session *dg.Session, message *dg.MessageCreate) (bool, error) {
	if message == nil || message.Message == nil || message.Author == nil || message.Author.Bot {
		return false, nil
	}
	if session == nil {
		return false, nil
	}

	query, ok := extractQuery(message.Content)
	if !ok {
		return false, nil
	}

	response := m.replyFor(query)
	if containsEmoji(response) {
		response = emojiFallback
	}

	if _, err := session.ChannelMessageSend(message.ChannelID, response); err != nil {
		m.log.Error("sending @grok reply", "err", err)
	}
	return true, nil
}

func extractQuery(content string) (string, bool) {
	location := grokTrigger.FindStringIndex(content)
	if location == nil {
		return "", false
	}
	query := content[:location[0]] + " " + content[location[1]:]
	return strings.TrimSpace(query), true
}

func (m *Grok) replyFor(query string) string {
	switch {
	case query == "":
		return m.choose(repliesGeneral)
	case isThisTrue.MatchString(query):
		return m.choose(repliesIsThisTrue)
	case query == "67":
		return m.choose(replies67)
	case isAllDigits(query):
		return m.choose(repliesNumbers)
	case strings.HasSuffix(query, "?"):
		return m.choose(repliesQuestions)
	default:
		return m.choose(repliesGeneral)
	}
}

func (m *Grok) choose(replies []string) string {
	if len(replies) == 0 {
		return ""
	}
	if m.pick == nil {
		return replies[rand.IntN(len(replies))]
	}
	index := m.pick(len(replies))
	if index < 0 || index >= len(replies) {
		index = 0
	}
	return replies[index]
}

func isAllDigits(value string) bool {
	if value == "" {
		return false
	}
	for _, r := range value {
		if !unicode.IsDigit(r) {
			return false
		}
	}
	return true
}

func containsEmoji(text string) bool {
	if customEmoji.MatchString(text) {
		return true
	}
	for _, r := range text {
		switch {
		case r >= 0x1F300 && r <= 0x1F5FF,
			r >= 0x1F600 && r <= 0x1F64F,
			r >= 0x1F680 && r <= 0x1F6FF,
			r >= 0x1F900 && r <= 0x1F9FF,
			r >= 0x1FA70 && r <= 0x1FAFF,
			r >= 0x2600 && r <= 0x26FF,
			r >= 0x2700 && r <= 0x27BF,
			r >= 0x1F1E6 && r <= 0x1F1FF:
			return true
		}
	}
	return false
}
