package analytics

import (
	"sort"
	"time"
)

// Report is the computed /analytics summary for one time window.
type Report struct {
	TotalMessages int64

	PeakHour  time.Time
	PeakCount int64

	MostActiveChannelID string
	MostActiveCount     int64
	MostActivePercent   float64

	Joins     int64
	Leaves    int64
	NetGrowth int64

	VoicePeak    int64
	VoiceAverage float64
	VoiceSamples int
}

// BuildReport filters the record to window ending at now and computes the
// same metrics as the Python /analytics command.
func (r Record) BuildReport(window time.Duration, now time.Time) Report {
	if window <= 0 {
		window = 24 * time.Hour
	}
	cutoff := now.Add(-window)
	cutoffTimestamp := float64(cutoff.UnixNano()) / 1e9

	hourTotals := make(map[string]int64)
	channelTotals := make(map[string]int64)
	var report Report

	for channelID, hours := range r.Messages {
		for hour, count := range hours {
			bucket, err := time.Parse(HourLayout, hour)
			if err != nil || bucket.Before(cutoff) {
				continue
			}
			report.TotalMessages += count
			hourTotals[hour] += count
			channelTotals[channelID] += count
		}
	}

	hourKeys := make([]string, 0, len(hourTotals))
	for hour := range hourTotals {
		hourKeys = append(hourKeys, hour)
	}
	sort.Strings(hourKeys)
	for _, hour := range hourKeys {
		count := hourTotals[hour]
		if count > report.PeakCount {
			report.PeakCount = count
			if parsed, err := time.Parse(HourLayout, hour); err == nil {
				report.PeakHour = parsed
			}
		}
	}

	channelIDs := make([]string, 0, len(channelTotals))
	for channelID := range channelTotals {
		channelIDs = append(channelIDs, channelID)
	}
	sort.Strings(channelIDs)
	for _, channelID := range channelIDs {
		count := channelTotals[channelID]
		if count > report.MostActiveCount {
			report.MostActiveCount = count
			report.MostActiveChannelID = channelID
		}
	}
	if report.TotalMessages > 0 {
		report.MostActivePercent = float64(report.MostActiveCount) / float64(report.TotalMessages) * 100
	}

	for _, event := range r.Churn {
		if event.Timestamp < cutoffTimestamp {
			continue
		}
		switch event.Event {
		case ChurnJoin:
			report.Joins++
		case ChurnLeave:
			report.Leaves++
		}
	}
	report.NetGrowth = report.Joins - report.Leaves

	var voiceSum int64
	for _, point := range r.Voice {
		if point.Timestamp < cutoffTimestamp {
			continue
		}
		report.VoiceSamples++
		voiceSum += point.Count
		if point.Count > report.VoicePeak {
			report.VoicePeak = point.Count
		}
	}
	if report.VoiceSamples > 0 {
		report.VoiceAverage = float64(voiceSum) / float64(report.VoiceSamples)
	}

	return report
}
