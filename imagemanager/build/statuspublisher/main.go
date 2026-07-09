// status-publisher writes Image Manager launcher rows to the EDA state DB
// (.cluster.apps.imagemanager.{app,status}) over a persistent StateDbUpdate
// stream, matching EDK dbStreamHandler.
//
// KEY AGGREGATOR SEMANTICS (verified against a live eda-sa):
//   - Rows are EPHEMERAL, scoped to the publishing stream: when the stream
//     closes (daemon restart, eda-sa restart, network blip) the aggregator
//     purges every row it received on that stream. The daemon therefore owns
//     the full desired row set and REPLAYS it on every (re)connected stream.
//   - Whole-table deletes (bare base path) are rejected ("unknown oneof
//     data_type"); only per-row predicate deletes ({.id=="x"}) are honored.
//   - There is no schema registration RPC: tables auto-create on first add.
//     (JsonSchemaRequest is a schema GET; sending create-style requests just
//     logs parse errors in eda-sa.)
//   - A send can block forever if the stream wedges, so every sync is
//     watchdog-guarded: on timeout the stream context is cancelled, the
//     stream is marked broken and rebuilt on the next tick.
package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	pb "imagemanager/statuspublisher/proto"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/protobuf/encoding/protojson"
)

const (
	defaultAggAddr   = "eda-sa.eda-system.svc:51100"
	defaultTLSClient = "/var/run/eda/tls/internal/client"
	defaultTLSTrust  = "/var/run/eda/tls/internal/trust/trust-bundle.pem"
	defaultSocket    = "/tmp/imagemanager-status.sock"
	statusBasePath   = ".cluster.apps.imagemanager.status"
	appBasePath      = ".cluster.apps.imagemanager.app"
)

// inputRow is a generic launcher row. Path selects the state DB table
// (defaults to statusBasePath); the remaining fields are passed through
// verbatim as the row JSON, so the two tables can carry different columns.
type inputRow struct {
	Path      string `json:"path,omitempty"`
	ID        string `json:"id"`
	Service   string `json:"service,omitempty"`
	Health    string `json:"health,omitempty"`
	HTTP      string `json:"http,omitempty"`
	Version   string `json:"version,omitempty"`
	Image     string `json:"image,omitempty"`
	Namespace string `json:"namespace,omitempty"`
	Status    string `json:"status,omitempty"`
	Open      string `json:"open,omitempty"`
	URL       string `json:"url,omitempty"`
	Details   string `json:"details,omitempty"`
}

type inputPayload struct {
	Adds    []inputRow `json:"adds"`
	Deletes []string   `json:"deletes"`
}

type publisher struct {
	mu       sync.Mutex
	client   pb.StateAggregatorIfClient
	conn     *grpc.ClientConn
	db       grpc.BidiStreamingClient[pb.StateDbRequest, pb.StateDbResponse]
	dbCancel context.CancelFunc // cancels the current stream (unwedges Send)
	gen      int                // stream generation; bumped on reconnect
	broken   bool               // set by recvLoop when the current stream dies
	// desired is the full launcher row set (jspath -> row JSON): the single
	// source of truth, replayed in full on every new stream because the
	// aggregator drops all rows when the previous stream ends.
	desired map[string]string
	// sent tracks what was actually published on the CURRENT stream, so a
	// payload diff produces predicate deletes only for rows that exist there.
	sent map[string]string
}

func main() {
	if len(os.Args) > 1 && os.Args[1] == "daemon" {
		if err := runDaemon(); err != nil {
			fmt.Fprintf(os.Stderr, "status-publisher: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if err := runOnce(); err != nil {
		fmt.Fprintf(os.Stderr, "status-publisher: %v\n", err)
		os.Exit(1)
	}
}

func runOnce() error {
	raw, err := io.ReadAll(os.Stdin)
	if err != nil {
		return fmt.Errorf("read stdin: %w", err)
	}
	sock := envOr("STATUS_PUBLISHER_SOCKET", defaultSocket)
	conn, err := net.DialTimeout("unix", sock, 3*time.Second)
	if err != nil {
		return fmt.Errorf("connect daemon at %s: %w (is status-publisher daemon running?)", sock, err)
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(12 * time.Second))
	if _, err := conn.Write(raw); err != nil {
		return err
	}
	// Half-close so the daemon's io.ReadAll sees EOF; without this the two
	// sides deadlock until a timeout fires (the old 25s-per-publish bug).
	if uc, ok := conn.(*net.UnixConn); ok {
		_ = uc.CloseWrite()
	}
	_ = conn.SetReadDeadline(time.Now().Add(12 * time.Second))
	resp, err := io.ReadAll(conn)
	if err != nil {
		return err
	}
	if len(resp) > 0 && resp[0] == 'E' {
		return fmt.Errorf("%s", strings.TrimSpace(string(resp)))
	}
	return nil
}

func runDaemon() error {
	sock := envOr("STATUS_PUBLISHER_SOCKET", defaultSocket)
	_ = os.Remove(sock)

	pub, err := newPublisher()
	if err != nil {
		return err
	}
	defer pub.close()

	ln, err := net.Listen("unix", sock)
	if err != nil {
		return err
	}
	defer ln.Close()
	_ = os.Chmod(sock, 0o666)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()

	go func() {
		<-ctx.Done()
		_ = ln.Close()
	}()

	for {
		conn, err := ln.Accept()
		if err != nil {
			select {
			case <-ctx.Done():
				return nil
			default:
				return err
			}
		}
		go handleClient(pub, conn)
	}
}

func handleClient(pub *publisher, conn net.Conn) {
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(30 * time.Second))
	raw, err := io.ReadAll(conn)
	if err != nil {
		_, _ = conn.Write([]byte("ERR read: " + err.Error()))
		return
	}
	var payload inputPayload
	if len(raw) > 0 {
		if err := json.Unmarshal(raw, &payload); err != nil {
			_, _ = conn.Write([]byte("ERR parse: " + err.Error()))
			return
		}
	}
	if err := pub.sync(payload); err != nil {
		_, _ = conn.Write([]byte("ERR " + err.Error()))
		return
	}
	_, _ = conn.Write([]byte("OK"))
}

func newPublisher() (*publisher, error) {
	p := &publisher{desired: map[string]string{}, sent: map[string]string{}}
	p.mu.Lock()
	defer p.mu.Unlock()
	if err := p.reconnect(); err != nil {
		return nil, err
	}
	return p, nil
}

func (p *publisher) close() {
	if p.dbCancel != nil {
		p.dbCancel()
	}
	if p.conn != nil {
		_ = p.conn.Close()
	}
}

func (p *publisher) recvLoop(stream grpc.BidiStreamingClient[pb.StateDbRequest, pb.StateDbResponse], gen int) {
	for {
		resp, err := stream.Recv()
		if err != nil {
			p.mu.Lock()
			if p.gen == gen {
				p.broken = true // next sync() reconnects before sending
			}
			p.mu.Unlock()
			fmt.Fprintf(os.Stderr, "status-publisher: stream gen %d ended: %v\n", gen, err)
			return
		}
		if upd := resp.GetUpdate(); upd != nil {
			// NOTE: our generated proto has the response adds/deletes field
			// numbers swapped vs the live aggregator, so treat both lists
			// identically and only look at jspath+error.
			for _, ent := range append(upd.GetAdds(), upd.GetDeletes()...) {
				if ent.GetError() != "" {
					fmt.Fprintf(os.Stderr, "status-publisher: aggregator error for %s: %s (hard=%v)\n",
						ent.GetJspath(), ent.GetError(), ent.GetIsHardError())
				}
			}
		}
		if debugEnabled() && resp != nil {
			b, _ := protojson.Marshal(resp)
			fmt.Fprintf(os.Stderr, "status-publisher: recv %s\n", b)
		}
	}
}

// reconnect (p.mu held) rebuilds the aggregator connection + StateDbUpdate
// stream and replays the full desired row set: the aggregator purged all our
// rows the moment the previous stream ended.
func (p *publisher) reconnect() error {
	if p.dbCancel != nil {
		p.dbCancel()
		p.dbCancel = nil
	}
	if p.conn != nil {
		_ = p.conn.Close()
		p.conn = nil
	}
	conn, err := dialAggregator()
	if err != nil {
		return fmt.Errorf("dial: %w", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	client := pb.NewStateAggregatorIfClient(conn)
	dbStream, err := client.StateDbUpdate(ctx)
	if err != nil {
		cancel()
		conn.Close()
		return fmt.Errorf("StateDbUpdate stream: %w", err)
	}
	p.client, p.conn, p.db, p.dbCancel = client, conn, dbStream, cancel
	p.gen++
	p.broken = false
	p.sent = map[string]string{} // fresh stream starts empty on the server
	go p.recvLoop(dbStream, p.gen)
	if err := p.flush(); err != nil {
		p.broken = true
		return fmt.Errorf("replay after reconnect: %w", err)
	}
	fmt.Fprintf(os.Stderr, "status-publisher: connected (gen %d), replayed %d row(s)\n",
		p.gen, len(p.desired))
	return nil
}

// sync ingests a client payload as the FULL desired state and pushes the diff.
func (p *publisher) sync(payload inputPayload) error {
	desired := map[string]string{}
	for _, row := range payload.Adds {
		if strings.TrimSpace(row.ID) == "" {
			continue
		}
		base := row.Path
		if base == "" {
			base = statusBasePath
		}
		rowCopy := row
		rowCopy.Path = "" // table path is addressing, not row data
		body, err := json.Marshal(rowCopy)
		if err != nil {
			return err
		}
		desired[fmt.Sprintf("%s{.id==%q}", base, row.ID)] = string(body)
	}

	p.mu.Lock()
	defer p.mu.Unlock()
	p.desired = desired
	if p.broken {
		return p.reconnect() // replays p.desired
	}
	if err := p.flush(); err != nil {
		// Stream likely broke (aggregator restart); rebuild + replay once.
		if rerr := p.reconnect(); rerr != nil {
			return fmt.Errorf("%v (reconnect failed: %v)", err, rerr)
		}
	}
	return nil
}

// flush (p.mu held) sends predicate deletes for rows gone from desired and
// (re)adds every changed row, updating p.sent. Guarded by a watchdog: a Send
// wedged on a dead stream is unblocked by cancelling the stream context.
func (p *publisher) flush() error {
	var reqs []*pb.StateDbRequest
	for jspath := range p.sent {
		if _, ok := p.desired[jspath]; !ok {
			reqs = append(reqs, &pb.StateDbRequest{
				ReqType: &pb.StateDbRequest_Update{
					Update: &pb.StateDbUpdateRequest{Deletes: []string{jspath}},
				},
			})
		}
	}
	for jspath, body := range p.desired {
		if p.sent[jspath] == body {
			continue
		}
		reqs = append(reqs, &pb.StateDbRequest{
			ReqType: &pb.StateDbRequest_Update{
				Update: &pb.StateDbUpdateRequest{
					Adds: []*pb.StateDbEntry{{
						Jspath:   jspath,
						DataType: &pb.StateDbEntry_Json{Json: body},
					}},
				},
			},
		})
	}
	if len(reqs) == 0 {
		return nil
	}

	done := make(chan error, 1)
	go func() {
		for _, req := range reqs {
			if err := p.db.Send(req); err != nil {
				done <- err
				return
			}
		}
		done <- nil
	}()
	select {
	case err := <-done:
		if err != nil {
			return fmt.Errorf("send: %w", err)
		}
	case <-time.After(10 * time.Second):
		// Wedged stream: cancel its context so the goroutine's Send returns,
		// and force a rebuild on the next attempt.
		if p.dbCancel != nil {
			p.dbCancel()
		}
		p.broken = true
		return fmt.Errorf("send timed out after 10s (stream cancelled)")
	}

	p.sent = map[string]string{}
	for k, v := range p.desired {
		p.sent[k] = v
	}
	return nil
}

func dialAggregator() (*grpc.ClientConn, error) {
	addr := envOr("EDA_AGGSVR_ADDR", defaultAggAddr)
	tlsCfg, err := loadTLS()
	if err != nil {
		return nil, err
	}
	return grpc.NewClient(addr, grpc.WithTransportCredentials(credentials.NewTLS(tlsCfg)))
}

func loadTLS() (*tls.Config, error) {
	clientDir := envOr("EDA_INTERNAL_TLS_CLIENT_DIR", defaultTLSClient)
	trustPath := envOr("EDA_INTERNAL_TLS_TRUST_BUNDLE", defaultTLSTrust)
	cert, err := tls.LoadX509KeyPair(clientDir+"/tls.crt", clientDir+"/tls.key")
	if err != nil {
		return nil, fmt.Errorf("load client cert: %w", err)
	}
	trustPEM, err := os.ReadFile(trustPath)
	if err != nil {
		return nil, fmt.Errorf("read trust bundle: %w", err)
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(trustPEM) {
		return nil, fmt.Errorf("parse trust bundle %s", trustPath)
	}
	return &tls.Config{
		Certificates: []tls.Certificate{cert},
		RootCAs:      pool,
		MinVersion:   tls.VersionTLS12,
		ServerName:   "internal.eda.nokia.com",
	}, nil
}

func debugEnabled() bool {
	debug := os.Getenv("STATUS_PUBLISHER_DEBUG")
	return debug == "1" || debug == "true"
}

func envOr(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}
