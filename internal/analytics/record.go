// Package analytics contains the analytics data model and the in-memory
// aggregator used by the Discord module.
package analytics

import "time"

// RetentionWindow mirrors the Python bot's 30-day analytics retention.
const RetentionWindow = 30 * 24 * time.Hour

// HourLayout is the UTC bucket key used by the Python analytics data.
const HourLayout = "2006-01-02T15:00:00Z"

// Churn event names.
const (
	ChurnJoin  = "join"
	ChurnLeave = "leave"
)

// Record is one guild's server_analytics row.
type Record struct {
	GuildID int64 `json:"-"`

	// Messages is channel ID -> UTC hour bucket -> message count.
	Messages map[string]map[string]int64 `json:"messages"`
	Churn    []ChurnEvent                `json:"churn"`
	Voice    []VoicePoint                `json:"voice"`
}

// ChurnEvent is a member join or leave.
type ChurnEvent struct {
	Event     string  `json:"event"`
	UserID    int64   `json:"user_id"`
	Timestamp float64 `json:"timestamp"`
}

// VoicePoint is a sampled count of non-bot members in voice channels.
type VoicePoint struct {
	Timestamp float64 `json:"timestamp"`
	Count     int64   `json:"count"`
}

// NewRecord returns an empty normalized record.
func NewRecord(guildID int64) Record {
	return Record{
		GuildID:  guildID,
		Messages: make(map[string]map[string]int64),
		Churn:    []ChurnEvent{},
		Voice:    []VoicePoint{},
	}
}

// Normalize fills nil maps/slices so JSON stays Python-compatible.
func (r *Record) Normalize(guildID int64) {
	if r.GuildID == 0 {
		r.GuildID = guildID
	}
	if r.Messages == nil {
		r.Messages = make(map[string]map[string]int64)
	}
	if r.Churn == nil {
		r.Churn = []ChurnEvent{}
	}
	if r.Voice == nil {
		r.Voice = []VoicePoint{}
	}
	for channelID, hours := range r.Messages {
		if hours == nil {
			r.Messages[channelID] = map[string]int64{}
		}
	}
}

// Clone returns a deep copy.
func (r Record) Clone() Record {
	out := r
	out.Messages = make(map[string]map[string]int64, len(r.Messages))
	for channelID, hours := range r.Messages {
		copied := make(map[string]int64, len(hours))
		for hour, count := range hours {
			copied[hour] = count
		}
		out.Messages[channelID] = copied
	}
	out.Churn = append([]ChurnEvent{}, r.Churn...)
	out.Voice = append([]VoicePoint{}, r.Voice...)
	return out
}

// HourKey returns the UTC hour bucket for at.
func HourKey(at time.Time) string {
	return at.UTC().Truncate(time.Hour).Format(HourLayout)
}

// AddMessage increments one channel/hour bucket.
func (r *Record) AddMessage(channelID string, at time.Time) {
	if channelID == "" {
		return
	}
	if r.Messages == nil {
		r.Messages = make(map[string]map[string]int64)
	}
	hours := r.Messages[channelID]
	if hours == nil {
		hours = make(map[string]int64)
		r.Messages[channelID] = hours
	}
	hours[HourKey(at)]++
}

// AddChurn appends a join or leave event.
func (r *Record) AddChurn(event string, userID int64, at time.Time) {
	r.Churn = append(r.Churn, ChurnEvent{
		Event:     event,
		UserID:    userID,
		Timestamp: float64(at.UnixNano()) / 1e9,
	})
}

// AddVoice appends a non-bot voice concurrency sample.
func (r *Record) AddVoice(count int64, at time.Time) {
	r.Voice = append(r.Voice, VoicePoint{
		Timestamp: float64(at.UnixNano()) / 1e9,
		Count:     count,
	})
}

// Prune drops message buckets, churn events, and voice samples older than
// cutoff. It mirrors clean_old_records in Python.
func (r *Record) Prune(cutoff time.Time) {
	for channelID, hours := range r.Messages {
		for hour := range hours {
			parsed, err := time.Parse(HourLayout, hour)
			if err != nil || parsed.Before(cutoff) {
				delete(hours, hour)
			}
		}
		if len(hours) == 0 {
			delete(r.Messages, channelID)
		}
	}

	cutoffTimestamp := float64(cutoff.UnixNano()) / 1e9
	churn := r.Churn[:0]
	for _, event := range r.Churn {
		if event.Timestamp >= cutoffTimestamp {
			churn = append(churn, event)
		}
	}
	r.Churn = churn

	voice := r.Voice[:0]
	for _, point := range r.Voice {
		if point.Timestamp >= cutoffTimestamp {
			voice = append(voice, point)
		}
	}
	r.Voice = voice
}
