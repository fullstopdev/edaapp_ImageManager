// status-publisher writes Image Manager launcher rows to EDA state DB
// (.cluster.apps.imagemanager.status), matching cable-map publishDashboardStatus
// via EDK dbStreamHandler (persistent bidi StateDbUpdate + StreamingJsonSchema).
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
)

type inputRow struct {
	ID      string `json:"id"`
	Service string `json:"service"`
	Status  string `json:"status"`
	Open    string `json:"open"`
	URL     string `json:"url"`
}

type inputPayload struct {
	Adds    []inputRow `json:"adds"`
	Deletes []string   `json:"deletes"`
}

type statusRow struct {
	ID      string `json:"id"`
	Service string `json:"service"`
	Status  string `json:"status"`
	Open    string `json:"open"`
	URL     string `json:"url"`
}

type publisher struct {
	mu     sync.Mutex
	client pb.StateAggregatorIfClient
	conn   *grpc.ClientConn
	db     grpc.BidiStreamingClient[pb.StateDbRequest, pb.StateDbResponse]
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
	_ = conn.SetDeadline(time.Now().Add(25 * time.Second))
	if _, err := conn.Write(raw); err != nil {
		return err
	}
	_ = conn.SetReadDeadline(time.Now().Add(25 * time.Second))
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
	conn, err := dialAggregator()
	if err != nil {
		return nil, err
	}
	client := pb.NewStateAggregatorIfClient(conn)
	ctx := context.Background()
	if err := registerSchema(ctx, client); err != nil {
		fmt.Fprintf(os.Stderr, "status-publisher: schema registration warning: %v\n", err)
	}
	if err := registerStreamingSchema(ctx, client); err != nil {
		fmt.Fprintf(os.Stderr, "status-publisher: streaming schema warning: %v\n", err)
	}
	dbStream, err := client.StateDbUpdate(ctx)
	if err != nil {
		conn.Close()
		return nil, fmt.Errorf("StateDbUpdate stream: %w", err)
	}
	p := &publisher{client: client, conn: conn, db: dbStream}
	go p.recvLoop()
	return p, nil
}

func (p *publisher) close() {
	if p.db != nil {
		_ = p.db.CloseSend()
	}
	if p.conn != nil {
		_ = p.conn.Close()
	}
}

func (p *publisher) recvLoop() {
	for {
		resp, err := p.db.Recv()
		if err != nil {
			if debugEnabled() {
				fmt.Fprintf(os.Stderr, "status-publisher: recv loop: %v\n", err)
			}
			return
		}
		if debugEnabled() && resp != nil {
			b, _ := protojson.Marshal(resp)
			fmt.Fprintf(os.Stderr, "status-publisher: recv %s\n", b)
		}
	}
}

func (p *publisher) sync(payload inputPayload) error {
	p.mu.Lock()
	defer p.mu.Unlock()

	for _, del := range payload.Deletes {
		if strings.TrimSpace(del) == "" {
			continue
		}
		req := &pb.StateDbRequest{
			ReqType: &pb.StateDbRequest_Update{
				Update: &pb.StateDbUpdateRequest{Deletes: []string{del}},
			},
		}
		if err := p.db.Send(req); err != nil {
			return fmt.Errorf("delete send: %w", err)
		}
	}

	for _, row := range payload.Adds {
		if strings.TrimSpace(row.ID) == "" {
			continue
		}
		body, err := json.Marshal(statusRow{
			ID:      row.ID,
			Service: row.Service,
			Status:  row.Status,
			Open:    row.Open,
			URL:     row.URL,
		})
		if err != nil {
			return err
		}
		jspath := fmt.Sprintf("%s{.id==%q}", statusBasePath, row.ID)
		req := &pb.StateDbRequest{
			ReqType: &pb.StateDbRequest_Update{
				Update: &pb.StateDbUpdateRequest{
					Adds: []*pb.StateDbEntry{{
						Jspath: jspath,
						DataType: &pb.StateDbEntry_Json{
							Json: string(body),
						},
					}},
				},
			},
		}
		if err := p.db.Send(req); err != nil {
			return fmt.Errorf("add %s send: %w", row.ID, err)
		}
	}
	return nil
}

func registerSchema(ctx context.Context, client pb.StateAggregatorIfClient) error {
	_, err := client.OneShotJsonSchema(ctx, &pb.OneShotJsonSchemaRequest{
		Request: &pb.JsonSchemaRequest{
			Jspath: statusBasePath,
			Type:   pb.JsonSchemaRequest_ReqType_REQ_TYPE_CREATE,
		},
	})
	if err != nil && !strings.Contains(strings.ToLower(err.Error()), "already") {
		return err
	}
	return nil
}

func registerStreamingSchema(ctx context.Context, client pb.StateAggregatorIfClient) error {
	stream, err := client.StreamingJsonSchema(ctx)
	if err != nil {
		return fmt.Errorf("StreamingJsonSchema: %w", err)
	}
	if err := stream.Send(&pb.StreamJsonSchemaRequest{
		PollType: &pb.StreamJsonSchemaRequest_Create{
			Create: &pb.StreamJsonSchemaGetRequest{
				Request: &pb.JsonSchemaRequest{
					Jspath: statusBasePath,
					Type:   pb.JsonSchemaRequest_ReqType_REQ_TYPE_CREATE,
				},
			},
		},
	}); err != nil {
		return fmt.Errorf("StreamingJsonSchema create: %w", err)
	}
	resp, err := stream.Recv()
	if err != nil && !strings.Contains(strings.ToLower(err.Error()), "already") {
		return fmt.Errorf("StreamingJsonSchema recv: %w", err)
	}
	if debugEnabled() && resp != nil {
		b, _ := protojson.Marshal(resp)
		fmt.Fprintf(os.Stderr, "status-publisher: schema %s\n", b)
	}
	go func() {
		for {
			if _, err := stream.Recv(); err != nil {
				return
			}
		}
	}()
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
