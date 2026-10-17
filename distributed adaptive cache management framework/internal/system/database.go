package system

import (
	"context"
	"errors"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("product not found")

type Database interface {
	Product(context.Context, int64) (Product, error)
	Ping(context.Context) error
	Close()
}
type Postgres struct{ Pool *pgxpool.Pool }

func OpenPostgres(ctx context.Context, url string) (*Postgres, error) {
	pool, e := pgxpool.New(ctx, url)
	if e != nil {
		return nil, e
	}
	if e = pool.Ping(ctx); e != nil {
		pool.Close()
		return nil, e
	}
	return &Postgres{pool}, nil
}
func (p *Postgres) Product(ctx context.Context, id int64) (Product, error) {
	var v Product
	e := p.Pool.QueryRow(ctx, "SELECT id,name,payload,version,updated_at FROM products WHERE id=$1", id).Scan(&v.ID, &v.Name, &v.Payload, &v.Version, &v.UpdatedAt)
	if errors.Is(e, pgx.ErrNoRows) {
		return v, ErrNotFound
	}
	return v, e
}
func (p *Postgres) Ping(ctx context.Context) error { return p.Pool.Ping(ctx) }
func (p *Postgres) Close()                         { p.Pool.Close() }
