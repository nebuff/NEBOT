package fun

import (
	"context"
	"fmt"
	"log/slog"
	"math"
	"regexp"
	"strconv"
	"strings"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/guild"
	"github.com/nebuff/n-bot/internal/module"
)

const nebuffInches = 54.0

var (
	nebuffPattern   = regexp.MustCompile(`(\d+(?:\.\d+)?)\s*(nebuffs?|nebuff's)\b`)
	feetInchPattern = regexp.MustCompile(`(\d+)\s*['"]\s*(\d+)(?:\s*(?:"|'|in|inches|inch))?`)
	unitPattern     = regexp.MustCompile(`(\d+(?:\.\d+)?)\s*(cm|m|meter|meters|in|inches|inch|ft|feet|f)\b`)
)

// Nebuff converts measurements to and from the fictional nebuff unit.
type Nebuff struct {
	module.Base
	guilds *guild.Cache
	log    *slog.Logger
}

// NewNebuff creates the @nebuff module.
func NewNebuff(guilds *guild.Cache, log *slog.Logger) *Nebuff {
	if guilds == nil {
		panic("fun: nil guild cache")
	}
	if log == nil {
		log = slog.Default()
	}
	return &Nebuff{guilds: guilds, log: log}
}

// Name implements module.Module.
func (m *Nebuff) Name() string { return "nebuff" }

// HandleMessage implements module.Module.
func (m *Nebuff) HandleMessage(ctx context.Context, session *dg.Session, message *dg.MessageCreate) (bool, error) {
	if message == nil || message.Message == nil || message.Author == nil || message.Author.Bot {
		return false, nil
	}
	if message.GuildID == "" || session == nil {
		return false, nil
	}

	guildID, err := strconv.ParseInt(message.GuildID, 10, 64)
	if err != nil {
		return false, nil
	}
	cfg, err := m.guilds.Get(ctx, guildID)
	if err != nil {
		m.log.Error("loading guild config for @nebuff", "guild_id", message.GuildID, "err", err)
		return false, nil
	}
	if !cfg.NebuffModuleEnabled {
		return false, nil
	}

	response, ok := convertNebuffText(strings.ToLower(message.Content))
	if !ok {
		return false, nil
	}

	if _, err := session.ChannelMessageSendReply(message.ChannelID, response, message.Reference()); err != nil {
		return false, nil
	}
	return true, nil
}

// convertNebuffText returns the same replies as the Python module. It checks
// nebuffs first, then feet/inches, then a general unit.
func convertNebuffText(text string) (string, bool) {
	if match := nebuffPattern.FindStringSubmatch(text); match != nil {
		value, err := strconv.ParseFloat(match[1], 64)
		if err != nil {
			return "", false
		}
		return fmt.Sprintf("That would be %s meters", formatPythonFloat(round2(value*1.3716))), true
	}

	if match := feetInchPattern.FindStringSubmatch(text); match != nil {
		feet, errFeet := strconv.ParseFloat(match[1], 64)
		inches, errInches := strconv.ParseFloat(match[2], 64)
		if errFeet != nil || errInches != nil {
			return "", false
		}
		totalInches := feet*12 + inches
		return fmt.Sprintf("That would be %s nebuff's", formatPythonFloat(round2(totalInches/nebuffInches))), true
	}

	if match := unitPattern.FindStringSubmatch(text); match != nil {
		value, err := strconv.ParseFloat(match[1], 64)
		if err != nil {
			return "", false
		}

		var totalInches float64
		switch match[2] {
		case "cm":
			totalInches = value / 2.54
		case "m", "meter", "meters":
			totalInches = value * 100 / 2.54
		case "in", "inches", "inch":
			totalInches = value
		case "ft", "feet", "f":
			totalInches = value * 12
		}
		return fmt.Sprintf("That would be %s nebuff's", formatPythonFloat(round2(totalInches/nebuffInches))), true
	}

	return "", false
}

func round2(value float64) float64 {
	return math.Round(value*100) / 100
}

// formatPythonFloat mimics str(float) for the values this module produces:
// two-decimal rounding, but "2.0" rather than "2.00".
func formatPythonFloat(value float64) string {
	formatted := strconv.FormatFloat(value, 'f', -1, 64)
	if !strings.ContainsAny(formatted, ".eE") {
		formatted += ".0"
	}
	return formatted
}
