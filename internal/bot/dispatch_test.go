package bot

import (
	"context"
	"io"
	"log/slog"
	"testing"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/module"
)

type joinRecorder struct {
	module.Base
	name    string
	handled bool
	calls   *[]string
}

func (m *joinRecorder) Name() string { return m.name }

func (m *joinRecorder) HandleMemberJoin(context.Context, *dg.Session, *dg.GuildMemberAdd) (bool, error) {
	*m.calls = append(*m.calls, m.name)
	return m.handled, nil
}

func TestMemberJoinDispatchStopsAfterHandledModule(t *testing.T) {
	var calls []string
	b := &Bot{
		log: slog.New(slog.NewTextHandler(io.Discard, nil)),
		modules: []module.Module{
			&joinRecorder{name: "first", handled: true, calls: &calls},
			&joinRecorder{name: "second", calls: &calls},
		},
	}

	b.onGuildMemberAdd(nil, &dg.GuildMemberAdd{
		Member: &dg.Member{User: &dg.User{ID: "1"}},
	})

	if len(calls) != 1 || calls[0] != "first" {
		t.Fatalf("calls = %v, want [first]", calls)
	}
}

func TestMemberJoinDispatchRunsAllWhenNotHandled(t *testing.T) {
	var calls []string
	b := &Bot{
		log: slog.New(slog.NewTextHandler(io.Discard, nil)),
		modules: []module.Module{
			&joinRecorder{name: "first", calls: &calls},
			&joinRecorder{name: "second", calls: &calls},
		},
	}

	b.onGuildMemberAdd(nil, &dg.GuildMemberAdd{
		Member: &dg.Member{User: &dg.User{ID: "1"}},
	})

	if len(calls) != 2 || calls[0] != "first" || calls[1] != "second" {
		t.Fatalf("calls = %v, want [first second]", calls)
	}
}
