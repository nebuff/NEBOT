package analytics

import (
	"testing"
	"time"
)

func TestRecordBuildReport(t *testing.T) {
	now := time.Date(2026, 11, 19, 12, 0, 0, 0, time.UTC)
	record := NewRecord(1)
	record.AddMessage("100", now.Add(-2*time.Hour))
	record.AddMessage("100", now.Add(-2*time.Hour))
	record.AddMessage("200", now.Add(-3*time.Hour))
	record.AddMessage("200", now.Add(-25*time.Hour))

	record.AddChurn(ChurnJoin, 1, now.Add(-time.Hour))
	record.AddChurn(ChurnJoin, 2, now.Add(-2*time.Hour))
	record.AddChurn(ChurnLeave, 3, now.Add(-time.Hour))
	record.AddChurn(ChurnJoin, 4, now.Add(-8*24*time.Hour))

	record.AddVoice(3, now.Add(-time.Hour))
	record.AddVoice(5, now.Add(-2*time.Hour))
	record.AddVoice(9, now.Add(-8*24*time.Hour))

	report := record.BuildReport(24*time.Hour, now)
	if report.TotalMessages != 3 {
		t.Errorf("TotalMessages = %d, want 3", report.TotalMessages)
	}
	if report.PeakCount != 2 || !report.PeakHour.Equal(now.Add(-2*time.Hour).Truncate(time.Hour)) {
		t.Errorf("peak = %s with %d, want 10:00 with 2", report.PeakHour, report.PeakCount)
	}
	if report.MostActiveChannelID != "100" || report.MostActiveCount != 2 {
		t.Errorf("most active = %s (%d), want 100 (2)", report.MostActiveChannelID, report.MostActiveCount)
	}
	if report.MostActivePercent < 66.6 || report.MostActivePercent > 66.7 {
		t.Errorf("MostActivePercent = %f", report.MostActivePercent)
	}
	if report.Joins != 2 || report.Leaves != 1 || report.NetGrowth != 1 {
		t.Errorf("churn = joins %d leaves %d net %d", report.Joins, report.Leaves, report.NetGrowth)
	}
	if report.VoicePeak != 5 || report.VoiceSamples != 2 || report.VoiceAverage != 4 {
		t.Errorf("voice = peak %d avg %f samples %d", report.VoicePeak, report.VoiceAverage, report.VoiceSamples)
	}
}

func TestRecordBuildReportEmpty(t *testing.T) {
	report := NewRecord(1).BuildReport(24*time.Hour, time.Now())
	if report.TotalMessages != 0 || report.PeakCount != 0 || report.MostActiveChannelID != "" {
		t.Errorf("empty report = %+v", report)
	}
	if report.Joins != 0 || report.Leaves != 0 || report.VoicePeak != 0 {
		t.Errorf("empty report churn/voice = %+v", report)
	}
}
